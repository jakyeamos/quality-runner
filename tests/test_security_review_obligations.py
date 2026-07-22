from __future__ import annotations

import json
from pathlib import Path

from quality_runner.security.review_obligations import (
    build_security_review_obligations,
    validate_security_review_obligations,
)
from quality_runner.workflow import run_payload
from test_support.quality_runner_fixtures import write_js_fixture


def test_security_review_obligations_are_stable_and_candidate_linked() -> None:
    payload = build_security_review_obligations(
        {
            "run_id": "obligation-test",
            "settings": {"enabled": True},
            "agent_review_gates": [
                {
                    "id": "security_api_route_auth_review",
                    "status": "review-required",
                    "scope": {"paths": ["app/api/**"], "categories": ["missing-auth"]},
                    "review_instructions": ["Review route guards."],
                    "completion_criteria": ["Record evidence."],
                },
                {
                    "id": "security_secret_exposure_review",
                    "status": "review-required",
                    "scope": {"paths": ["**/*"], "categories": ["secret-in-log"]},
                    "review_instructions": ["Review secrets."],
                    "completion_criteria": ["Document disposition."],
                },
            ],
            "candidates": [
                {
                    "id": "SEC-1",
                    "category": "missing-auth",
                    "file": "app/api/users/route.ts",
                    "line": 4,
                    "fingerprint": "fp-1",
                    "severity_hint": "high",
                },
                {
                    "id": "SEC-2",
                    "category": "secret-in-log",
                    "file": "lib/logging.ts",
                    "line": 8,
                    "fingerprint": "fp-2",
                    "severity_hint": "medium",
                },
            ],
        }
    )

    assert payload["schema"] == "quality-runner-security-review-obligations-v0.1"
    assert payload["obligation_count"] == 2
    assert [item["id"] for item in payload["obligations"]] == [
        "security_api_route_auth_review",
        "security_secret_exposure_review",
    ]
    assert payload["obligations"][0]["candidate_refs"][0]["id"] == "SEC-1"
    assert payload["obligations"][1]["candidate_refs"][0]["id"] == "SEC-2"
    assert validate_security_review_obligations(payload)["passed"] is True


def test_empty_security_review_obligations_are_explicitly_valid() -> None:
    payload = build_security_review_obligations(
        {"settings": {"enabled": False}, "agent_review_gates": [], "candidates": []}
    )

    assert payload["status"] == "disabled"
    assert payload["obligation_count"] == 0
    assert validate_security_review_obligations(payload)["passed"] is True


def test_run_emits_obligation_artifact_and_handoff_records(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    api_dir = tmp_path / "app" / "api" / "users"
    api_dir.mkdir(parents=True)
    (api_dir / "route.ts").write_text(
        "export async function GET() { return Response.json({ ok: true }); }\n",
        encoding="utf-8",
    )

    payload = run_payload(repo_root=tmp_path, run_id="obligation-artifact", profile="default")
    artifact_path = Path(payload["artifact_paths"]["security_review_obligations_json"])
    obligations = json.loads(artifact_path.read_text(encoding="utf-8"))
    handoff = json.loads(
        Path(payload["artifact_paths"]["agent_handoff_json"]).read_text(encoding="utf-8")
    )

    assert artifact_path.name == "security-review-obligations.json"
    assert obligations["obligation_count"] >= 2
    assert "security_api_route_auth_review" in {item["id"] for item in obligations["obligations"]}
    assert handoff["security_review"]["review_obligation_count"] == obligations["obligation_count"]
