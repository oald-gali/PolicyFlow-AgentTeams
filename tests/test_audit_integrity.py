from __future__ import annotations

import io
import json
import zipfile

from policyflow.models import CreateRunPayload
from policyflow.utils import verify_trace_chain

from conftest import custom_request, start_scenario


def _zip_files(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _rewrite_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_trace_hash_chain_is_valid_and_persists(runtime):
    record = start_scenario(runtime, "compliant")

    valid, error, head = verify_trace_chain(record.trace)
    reloaded = runtime.get_run(record.run_id)

    assert valid is True
    assert error is None
    assert head == record.trace[-1].event_hash
    assert reloaded.trace[-1].event_hash == head


def test_trace_mutation_is_detected(runtime):
    record = start_scenario(runtime, "compliant")
    tampered = record.model_copy(deep=True)
    tampered.trace[1].summary = "攻击者改写了制度检索结果"

    valid, error, _ = verify_trace_chain(tampered.trace)

    assert valid is False
    assert "invalid event_hash" in error


def test_audit_bundle_manifest_and_trace_verify(runtime):
    record = start_scenario(runtime, "over_limit")
    bundle = runtime.audit_bundle(record.run_id)

    result = runtime.verify_audit_bundle(bundle)
    files = _zip_files(bundle)
    manifest = json.loads(files["MANIFEST.json"])

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["file_count"] == 6
    assert result["algorithm"] == "SHA-256"
    assert set(manifest["files"]) == {
        "run.json",
        "trace.jsonl",
        "audit-report.md",
        "policy-snapshot.md",
        "case-lesson.json",
        "trace-otel-genai.json",
    }
    assert manifest["trace_chain_head"] == record.trace[-1].event_hash


def test_audit_bundle_contains_unpromoted_case_lesson(runtime):
    record = start_scenario(runtime, "missing_invoice")
    files = _zip_files(runtime.audit_bundle(record.run_id))
    lesson = json.loads(files["case-lesson.json"])

    assert lesson["format"] == "policyflow-case-lesson/v1"
    assert lesson["source_run_id"] == record.run_id
    assert lesson["lesson_type"] == "policy_block"
    assert lesson["promotion"] == {
        "status": "candidate",
        "requires_human_review": True,
        "target": "data/scenarios.json and tests/",
    }
    assert lesson["regression_candidate"]["assertions"][
        "blocked_runs_have_no_writes"
    ] is True


def test_audit_bundle_file_tampering_is_detected(runtime):
    record = start_scenario(runtime, "compliant")
    files = _zip_files(runtime.audit_bundle(record.run_id))
    run_payload = json.loads(files["run.json"])
    run_payload["status"] = "verified"
    files["run.json"] = json.dumps(run_payload).encode("utf-8")

    result = runtime.verify_audit_bundle(_rewrite_zip(files))

    assert result["valid"] is False
    assert "run.json hash mismatch" in result["errors"]


def test_audit_bundle_trace_tampering_is_detected_by_hash_and_chain(runtime):
    record = start_scenario(runtime, "compliant")
    files = _zip_files(runtime.audit_bundle(record.run_id))
    trace_lines = files["trace.jsonl"].decode("utf-8").splitlines()
    event = json.loads(trace_lines[1])
    event["summary"] = "篡改后的审计事件"
    trace_lines[1] = json.dumps(event, ensure_ascii=False)
    files["trace.jsonl"] = ("\n".join(trace_lines) + "\n").encode("utf-8")

    result = runtime.verify_audit_bundle(_rewrite_zip(files))

    assert result["valid"] is False
    assert "trace.jsonl hash mismatch" in result["errors"]
    assert any("trace event 1" in error for error in result["errors"])


def test_audit_bundle_rejects_missing_manifest(runtime):
    record = start_scenario(runtime, "compliant")
    files = _zip_files(runtime.audit_bundle(record.run_id))
    files.pop("MANIFEST.json")

    result = runtime.verify_audit_bundle(_rewrite_zip(files))

    assert result == {"valid": False, "errors": ["MANIFEST.json is missing"]}


def test_audit_export_redacts_credentials_phone_and_employee_id(runtime):
    request = custom_request(
        employee_id="EMP-SECRET-99",
        request_text=(
            "报销杭州测试差旅，联系电话 13812345678，"
            "临时凭据 Bearer top.secret-token_123，发票齐全。"
        ),
    )
    record = runtime.create_run(CreateRunPayload(request=request))

    bundle = runtime.audit_bundle(record.run_id)
    exported = _zip_files(bundle)["run.json"].decode("utf-8")

    assert "top.secret-token_123" not in exported
    assert "13812345678" not in exported
    assert "EMP-SECRET-99" not in exported
    assert "Bearer [REDACTED]" in exported
    assert "1**********" in exported
    assert "EMP-***99" in exported
