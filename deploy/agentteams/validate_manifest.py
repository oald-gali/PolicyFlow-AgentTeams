from __future__ import annotations

import argparse
import base64
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

import jsonschema
import yaml


AGENTTEAMS_VERSION = "v1.2.2"
AGENTTEAMS_COMMIT = "849182af8e017168a5a200a87b1062142caf462d"
CRD_FILES = {
    "Worker": ("workers.agentteams.io.yaml", "a302bd7f3a5b28f88df0dc2f4ae955b7b82592bc"),
    "Team": ("teams.agentteams.io.yaml", "981ef73d5370e5768c00b775c03ca6a911728184"),
    "Human": ("humans.agentteams.io.yaml", "63f64f8093b0758a88e23d0bd3ab04b7bd8d69be"),
}
EXPECTED_HUMANS = {
    "department-manager": "Department Manager",
    "finance-reviewer": "Finance Reviewer",
}


def load_skill_metadata(skill_path: Path) -> dict[str, str]:
    text = skill_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise ValueError("SKILL.md frontmatter is not closed")
    metadata = yaml.safe_load(parts[1])
    if not isinstance(metadata, dict):
        raise ValueError("SKILL.md frontmatter must be a mapping")
    return {
        str(key): value.strip() if isinstance(value, str) else ""
        for key, value in metadata.items()
    }


def fetch_crd(filename: str, blob_sha: str) -> tuple[dict[str, Any], str, str]:
    source_url = (
        "https://raw.githubusercontent.com/agentscope-ai/AgentTeams/"
        f"{AGENTTEAMS_COMMIT}/agentteams-controller/config/crd/{filename}"
    )
    api_url = f"https://api.github.com/repos/agentscope-ai/AgentTeams/git/blobs/{blob_sha}"
    request = urllib.request.Request(
        api_url,
        headers={"User-Agent": "PolicyFlow-GOAI-MVP", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    content = base64.b64decode(payload["content"])
    return yaml.safe_load(content), source_url, hashlib.sha256(content).hexdigest()


def schema_for(crd: dict[str, Any]) -> dict[str, Any]:
    versions = crd.get("spec", {}).get("versions", [])
    version = next((item for item in versions if item.get("name") == "v1beta1"), None)
    if version is None:
        raise ValueError("official CRD does not expose v1beta1")
    return version["schema"]["openAPIV3Schema"]


def validate(manifest_path: Path, project_root: Path) -> dict[str, Any]:
    documents = [item for item in yaml.safe_load_all(manifest_path.read_text(encoding="utf-8")) if item]
    sources: dict[str, dict[str, str]] = {}
    schemas: dict[str, dict[str, Any]] = {}
    for kind, (filename, blob_sha) in CRD_FILES.items():
        crd, url, digest = fetch_crd(filename, blob_sha)
        schemas[kind] = schema_for(crd)
        sources[kind] = {"url": url, "git_blob_sha": blob_sha, "sha256": digest}

    errors: list[str] = []
    validated: list[dict[str, str]] = []
    for index, document in enumerate(documents, start=1):
        kind = document.get("kind")
        name = document.get("metadata", {}).get("name", "<missing>")
        if document.get("apiVersion") != "agentteams.io/v1beta1":
            errors.append(f"document {index} {kind}/{name}: apiVersion is not agentteams.io/v1beta1")
            continue
        if kind not in schemas:
            errors.append(f"document {index} {kind}/{name}: unsupported kind")
            continue
        try:
            jsonschema.validate(document, schemas[kind])
        except jsonschema.ValidationError as error:
            path = ".".join(str(item) for item in error.absolute_path)
            errors.append(f"document {index} {kind}/{name} at {path or '<root>'}: {error.message}")
        else:
            validated.append({"kind": kind, "name": name})

    workers = [item for item in documents if item.get("kind") == "Worker"]
    teams = [item for item in documents if item.get("kind") == "Team"]
    humans = [item for item in documents if item.get("kind") == "Human"]
    if len(workers) != 4:
        errors.append("semantic: exactly four Worker resources are required for PolicyFlow")
    if len(teams) != 1:
        errors.append("semantic: exactly one Team is required for the MVP")
    else:
        members = teams[0].get("spec", {}).get("workerMembers", [])
        leaders = [item for item in members if item.get("role") == "team_leader"]
        worker_names = {item.get("metadata", {}).get("name") for item in workers}
        member_names = {item.get("name") for item in members}
        if len(leaders) != 1:
            errors.append("semantic: Team must have exactly one team_leader")
        if member_names != worker_names:
            errors.append("semantic: Team.workerMembers must reference every Worker exactly once")
    human_by_name = {
        item.get("metadata", {}).get("name"): item
        for item in humans
    }
    if len(humans) != 2:
        errors.append("semantic: exactly two independent Human resources are required")
    if set(human_by_name) != set(EXPECTED_HUMANS):
        errors.append(
            "semantic: Human resources must be exactly department-manager and finance-reviewer"
        )
    for name, display_name in EXPECTED_HUMANS.items():
        human = human_by_name.get(name)
        if human is None:
            continue
        spec = human.get("spec", {})
        if spec.get("displayName") != display_name:
            errors.append(f"semantic: Human/{name} displayName must be {display_name}")
        if spec.get("permissionLevel") != 2:
            errors.append(f"semantic: Human/{name} permissionLevel must be 2")
        if spec.get("accessibleTeams") != ["policyflow-team"]:
            errors.append(
                f"semantic: Human/{name} must be scoped only to policyflow-team"
            )

    mcp_workers = [
        item["metadata"]["name"]
        for item in workers
        if item.get("spec", {}).get("mcpServers")
    ]
    if mcp_workers != ["policyflow-executor"]:
        errors.append("semantic: only policyflow-executor may declare the action MCP server")

    assigned_skills = {
        skill
        for worker in workers
        for skill in worker.get("spec", {}).get("skills", [])
    }
    missing_skills = sorted(
        skill for skill in assigned_skills if not (project_root / "skills" / skill / "SKILL.md").is_file()
    )
    if missing_skills:
        errors.append("semantic: missing SKILL.md for " + ", ".join(missing_skills))

    valid_skill_packages: list[str] = []
    for skill in sorted(assigned_skills):
        skill_path = project_root / "skills" / skill / "SKILL.md"
        if not skill_path.is_file():
            continue
        try:
            metadata = load_skill_metadata(skill_path)
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
            errors.append(f"semantic: Skill/{skill} metadata invalid: {error}")
            continue
        if metadata.get("name") != skill:
            errors.append(f"semantic: Skill/{skill} frontmatter name must match directory")
            continue
        missing_fields = [
            field
            for field in ("description", "assign_when")
            if not metadata.get(field)
        ]
        if missing_fields:
            errors.append(
                f"semantic: Skill/{skill} missing frontmatter fields: {', '.join(missing_fields)}"
            )
            continue
        valid_skill_packages.append(skill)

    return {
        "valid": not errors,
        "agentteams_version": AGENTTEAMS_VERSION,
        "agentteams_commit": AGENTTEAMS_COMMIT,
        "manifest": str(manifest_path),
        "documents": len(documents),
        "validated_count": len(validated),
        "validated_resources": validated,
        "workers": len(workers),
        "humans": len(humans),
        "human_names": sorted(name for name in human_by_name if name),
        "team_leaders": 1 if teams and len([item for item in teams[0].get("spec", {}).get("workerMembers", []) if item.get("role") == "team_leader"]) == 1 else 0,
        "mcp_workers": mcp_workers,
        "assigned_skills": sorted(assigned_skills),
        "valid_skill_packages": valid_skill_packages,
        "official_crd_sources": sources,
        "errors": errors,
        "scope": "schema, static semantics and Worker Skill package metadata; not a live AgentTeams/Matrix or Skill distribution run",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PolicyFlow against pinned AgentTeams CRDs")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[2]
    result = validate(Path(__file__).with_name("policyflow-team.yaml"), project_root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        state = "PASS" if result["valid"] else "FAIL"
        print(f"{state}: AgentTeams {result['agentteams_version']} manifest validation")
        print(
            f"resources={result['validated_count']}/{result['documents']} "
            f"workers={result['workers']} humans={result['humans']} "
            f"skills={len(result['valid_skill_packages'])}/{len(result['assigned_skills'])}"
        )
        for error in result["errors"]:
            print(f"- {error}")
        print(f"scope: {result['scope']}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
