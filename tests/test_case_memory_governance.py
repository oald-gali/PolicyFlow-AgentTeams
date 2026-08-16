from __future__ import annotations

import io
import json
import zipfile

import pytest

from policyflow import api
from policyflow.auth import ApprovalIdentityError
from policyflow.models import LessonReviewPayload, LessonReviewSessionPayload
from policyflow.runtime import PolicyFlowRuntime, RuntimeConflictError

from conftest import PROJECT_ROOT, start_scenario


def _review(runtime, run_id: str, decision: str = "approve"):
    session = runtime.issue_demo_lesson_review_session(
        "operator-wu", run_id, decision
    )
    result = runtime.review_case_lesson(
        run_id,
        LessonReviewPayload(
            decision=decision,
            review_token=session["approval_token"],
            reason="具名人工复核了制度证据、结果和回归断言。",
        ),
    )
    return session, result


def _zip_files(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_candidate_is_not_dataset_entry_and_only_operator_can_mint_token(runtime):
    record = start_scenario(runtime, "missing_invoice")

    lesson = runtime.case_lesson(record.run_id)
    dataset = runtime.case_memory_dataset()

    assert lesson["promotion"]["status"] == "candidate"
    assert lesson["promotion"]["requires_human_review"] is True
    assert dataset["revision"] == 0
    assert dataset["entries"] == []
    with pytest.raises(ApprovalIdentityError, match="Workflow Operator"):
        runtime.issue_demo_lesson_review_session(
            "finance-lin", record.run_id, "approve"
        )


def test_signed_approval_promotes_one_versioned_entry_and_is_auditable(runtime):
    record = start_scenario(runtime, "missing_invoice")
    session, lesson = _review(runtime, record.run_id)

    dataset = runtime.case_memory_dataset()
    persisted = runtime.get_run(record.run_id)
    files = _zip_files(runtime.audit_bundle(record.run_id))
    exported_lesson = json.loads(files["case-lesson.json"])
    exported_dataset = json.loads(files["case-memory-dataset.json"])

    assert session["lesson_id"] == lesson["lesson_id"]
    assert session["target_revision"] == 1
    assert lesson["promotion"]["status"] == "promoted"
    assert lesson["promotion"]["dataset_revision"] == 1
    assert lesson["promotion"]["review"]["principal_id"] == "operator-wu"
    assert lesson["promotion"]["review"]["actor"] == "Wu R."
    assert lesson["promotion"]["review"]["actor_role"] == "Workflow Operator"
    assert lesson["promotion"]["automatic_policy_or_skill_mutation"] is False
    assert dataset["revision"] == 1
    assert dataset["entry_count"] == 1
    assert dataset["entries"][0]["lesson_id"] == lesson["lesson_id"]
    assert dataset["governance"]["automatic_policy_mutation"] is False
    assert dataset["governance"]["automatic_skill_mutation"] is False
    assert persisted.trace[-1].name == "case_lesson.approve"
    assert persisted.trace[-1].arguments_hash == session["review_binding_hash"]
    assert exported_lesson["promotion"]["status"] == "promoted"
    assert exported_dataset["revision"] == 1
    assert runtime.verify_audit_bundle(runtime.audit_bundle(record.run_id))["valid"] is True


def test_signed_rejection_is_persisted_but_never_enters_dataset(runtime):
    record = start_scenario(runtime, "missing_invoice")
    _, lesson = _review(runtime, record.run_id, "reject")

    dataset = runtime.case_memory_dataset()
    files = _zip_files(runtime.audit_bundle(record.run_id))
    report = files["audit-report.md"].decode("utf-8")

    assert lesson["promotion"]["status"] == "rejected"
    assert lesson["promotion"]["dataset_revision"] is None
    assert lesson["promotion"]["review"]["decision"] == "reject"
    assert dataset["revision"] == 0
    assert dataset["entries"] == []
    assert "case-memory-dataset.json" not in files
    assert "Wu R.（Workflow Operator）" in report
    assert "自动改写政策或 Skill：`false`" in report


def test_review_token_cannot_be_swapped_from_approve_to_reject(runtime):
    record = start_scenario(runtime, "missing_invoice")
    session = runtime.issue_demo_lesson_review_session(
        "operator-wu", record.run_id, "approve"
    )

    with pytest.raises(RuntimeConflictError, match="bound"):
        runtime.review_case_lesson(
            record.run_id,
            LessonReviewPayload(
                decision="reject",
                review_token=session["approval_token"],
                reason="尝试把 approve 凭证替换为 reject 决策。",
            ),
        )

    assert runtime.case_memory_dataset()["entries"] == []


def test_review_token_cannot_cross_runs(runtime):
    first = start_scenario(runtime, "missing_invoice")
    second = start_scenario(runtime, "query_only")
    session = runtime.issue_demo_lesson_review_session(
        "operator-wu", first.run_id, "approve"
    )

    with pytest.raises(RuntimeConflictError, match="bound"):
        runtime.review_case_lesson(
            second.run_id,
            LessonReviewPayload(
                decision="approve",
                review_token=session["approval_token"],
                reason="尝试跨 Run 复用签名凭证。",
            ),
        )

    assert runtime.case_memory_dataset()["entries"] == []


def test_review_token_is_single_use(runtime):
    record = start_scenario(runtime, "missing_invoice")
    session, _ = _review(runtime, record.run_id)

    with pytest.raises(RuntimeConflictError, match="already"):
        runtime.review_case_lesson(
            record.run_id,
            LessonReviewPayload(
                decision="approve",
                review_token=session["approval_token"],
                reason="尝试重放已经成功使用的评审凭证。",
            ),
        )

    assert runtime.case_memory_dataset()["entry_count"] == 1


def test_stale_dataset_revision_requires_a_fresh_token(runtime):
    first = start_scenario(runtime, "missing_invoice")
    second = start_scenario(runtime, "query_only")
    first_session = runtime.issue_demo_lesson_review_session(
        "operator-wu", first.run_id, "approve"
    )
    stale_session = runtime.issue_demo_lesson_review_session(
        "operator-wu", second.run_id, "approve"
    )
    assert first_session["base_revision"] == stale_session["base_revision"] == 0

    runtime.review_case_lesson(
        first.run_id,
        LessonReviewPayload(
            decision="approve",
            review_token=first_session["approval_token"],
            reason="先接受第一条候选并推进数据集版本。",
        ),
    )
    with pytest.raises(RuntimeConflictError, match="bound"):
        runtime.review_case_lesson(
            second.run_id,
            LessonReviewPayload(
                decision="approve",
                review_token=stale_session["approval_token"],
                reason="旧 token 不得写入已经变化的数据集版本。",
            ),
        )

    fresh_session = runtime.issue_demo_lesson_review_session(
        "operator-wu", second.run_id, "approve"
    )
    assert fresh_session["base_revision"] == 1
    assert fresh_session["target_revision"] == 2


def test_review_and_dataset_survive_restart_and_api_surface_is_wired(
    db_path, monkeypatch
):
    first = PolicyFlowRuntime(PROJECT_ROOT, db_path=db_path)
    record = start_scenario(first, "missing_invoice")
    _review(first, record.run_id)
    first.store.close()

    restarted = PolicyFlowRuntime(PROJECT_ROOT, db_path=db_path)
    monkeypatch.setattr(api, "runtime", restarted)
    try:
        lesson = api.get_case_lesson(record.run_id)
        dataset = api.case_memory_dataset()

        assert lesson["promotion"]["status"] == "promoted"
        assert dataset["revision"] == 1
        assert dataset["entries"][0]["source_run_id"] == record.run_id

        next_record = start_scenario(restarted, "query_only")
        session = api.demo_lesson_review_session(
            next_record.run_id,
            LessonReviewSessionPayload(
                reviewer_id="operator-wu", decision="reject"
            ),
        )
        rejected = api.review_case_lesson(
            next_record.run_id,
            LessonReviewPayload(
                decision="reject",
                review_token=session["approval_token"],
                reason="通过 API 接口完成具名拒绝。",
            ),
        )
        assert rejected["promotion"]["status"] == "rejected"
        assert api.case_memory_dataset()["entry_count"] == 1
    finally:
        restarted.store.close()


def test_nonterminal_run_cannot_enter_lesson_review(runtime):
    waiting = start_scenario(runtime, "compliant")

    with pytest.raises(RuntimeConflictError, match="terminal"):
        runtime.issue_demo_lesson_review_session(
            "operator-wu", waiting.run_id, "approve"
        )
