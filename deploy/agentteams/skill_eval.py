from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from policyflow.evaluation import run_golden_suite  # noqa: E402
from policyflow.runtime import PolicyFlowRuntime  # noqa: E402


def evaluate_skills() -> dict[str, Any]:
    specification = json.loads(
        (PROJECT_ROOT / "data" / "skill_eval_v1.json").read_text(encoding="utf-8")
    )
    configured = specification.get("skills", {})
    available = {
        path.parent.name
        for path in (PROJECT_ROOT / "skills").glob("*/SKILL.md")
    }
    errors: list[str] = []
    if set(configured) != available:
        errors.append(
            "Skill eval inventory differs from skills/*/SKILL.md: "
            f"configured={sorted(configured)} available={sorted(available)}"
        )

    with tempfile.TemporaryDirectory(prefix="policyflow-skill-eval-") as temp_dir:
        runtime = PolicyFlowRuntime(PROJECT_ROOT, Path(temp_dir) / "eval.db")
        try:
            suite = run_golden_suite(runtime)
        finally:
            runtime.store.close()

    case_results = {item["case_id"]: bool(item["passed"]) for item in suite["cases"]}
    associations = 0
    skill_results: list[dict[str, Any]] = []
    for skill, case_ids in configured.items():
        associations += len(case_ids)
        missing = [case_id for case_id in case_ids if case_id not in case_results]
        failed = [case_id for case_id in case_ids if case_results.get(case_id) is False]
        if missing:
            errors.append(f"{skill}: unknown cases: {', '.join(missing)}")
        if failed:
            errors.append(f"{skill}: failed cases: {', '.join(failed)}")
        skill_results.append(
            {
                "skill": skill,
                "passed": not missing and not failed,
                "cases": case_ids,
            }
        )

    skills_passed = sum(1 for item in skill_results if item["passed"])
    associations_passed = sum(
        1
        for item in skill_results
        for case_id in item["cases"]
        if case_results.get(case_id) is True
    )
    return {
        "format": specification["format"],
        "method": specification["method"],
        "limitations": specification["limitations"],
        "valid": not errors and skills_passed == len(skill_results),
        "skills_passed": skills_passed,
        "skills_total": len(skill_results),
        "associations_passed": associations_passed,
        "associations_total": associations,
        "golden_passed": suite["passed"],
        "golden_total": suite["total"],
        "attack_blocked": suite["attack_blocked"],
        "attack_total": suite["attack_total"],
        "skill_results": skill_results,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate every PolicyFlow Skill against mapped deterministic Golden cases"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    result = evaluate_skills()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        state = "PASS" if result["valid"] else "FAIL"
        print(
            f"{state}: skills={result['skills_passed']}/{result['skills_total']} "
            f"associations={result['associations_passed']}/{result['associations_total']} "
            f"golden={result['golden_passed']}/{result['golden_total']} "
            f"attacks={result['attack_blocked']}/{result['attack_total']}"
        )
        print(f"method: {result['method']}")
        print(f"boundary: {result['limitations']}")
        for error in result["errors"]:
            print(f"- {error}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
