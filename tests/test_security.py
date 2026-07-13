from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quality_runner.config import load_repo_config
from quality_runner.security.candidates import security_candidate_fingerprint
from quality_runner.security.config import security_settings
from quality_runner.security.scan import merge_security_into_capability_map
from quality_runner.workflow import inspect_payload, run_payload, verify_gates_payload
from test_support.quality_runner_fixtures import write_js_fixture, write_python_quality_fixture
from test_support.security_scan import run_security_scan


def _run_scan(repo: Path, config_text: str | None = None) -> dict:
    return run_security_scan(repo, config_text)


def test_security_capability_detected_from_package_script(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    package = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    package["scripts"]["gitleaks"] = "gitleaks detect --source ."
    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")

    security_scan = _run_scan(tmp_path)
    available_ids = {item["id"] for item in security_scan["available_capabilities"]}
    assert "security_secrets_scan" in available_ids


def test_missing_dependency_audit_for_js_project(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    security_scan = _run_scan(tmp_path)
    missing_ids = {item["id"] for item in security_scan["missing_capabilities"]}
    assert "security_dependency_audit" in missing_ids


def test_missing_dependency_audit_for_python_project(tmp_path: Path) -> None:
    write_python_quality_fixture(tmp_path)
    security_scan = _run_scan(tmp_path)
    missing_ids = {item["id"] for item in security_scan["missing_capabilities"]}
    assert "security_dependency_audit" in missing_ids


def test_security_scan_artifact_shape(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    security_scan = _run_scan(tmp_path)
    assert security_scan["schema"] == "quality-runner-security-scan-v0.1"
    assert "summary" in security_scan
    assert "taxonomy" in security_scan
    assert "candidates" in security_scan
    assert "agent_review_gates" in security_scan
    assert isinstance(security_scan["taxonomy"]["categories"], list)


def test_candidate_detection_for_dangerous_sink(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "unsafe.js").write_text("const x = eval(userInput);\n", encoding="utf-8")
    security_scan = _run_scan(tmp_path)
    categories = {item["category"] for item in security_scan["candidates"]}
    assert "dangerous-sink" in categories


def test_candidate_detection_for_secret_exposure(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "secrets.js").write_text(
        'const apiKey = "example-placeholder-not-a-real-secret";\n',
        encoding="utf-8",
    )
    security_scan = _run_scan(tmp_path)
    categories = {item["category"] for item in security_scan["candidates"]}
    assert "secrets-exposure" in categories


def test_secret_candidate_evidence_is_redacted_before_artifact_persistence(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    secret = "m7-security-redaction-regression-secret-42"
    src = tmp_path / "src"
    src.mkdir()
    (src / "secrets.js").write_text(f'const apiKey = "{secret}";\n', encoding="utf-8")

    payload = run_payload(repo_root=tmp_path, run_id="sec-redaction-001", profile="default")
    security_scan = json.loads(
        Path(payload["artifact_paths"]["security_scan_json"]).read_text(encoding="utf-8")
    )
    candidate = next(
        item for item in security_scan["candidates"] if item["category"] == "secrets-exposure"
    )

    assert candidate["evidence"] == 'const apiKey = "<redacted>";'
    assert candidate["fingerprint"] == security_candidate_fingerprint(
        category="secrets-exposure",
        file="src/secrets.js",
        line=1,
        evidence=candidate["evidence"],
    )
    artifact_texts = [
        path.read_text(encoding="utf-8")
        for path in (tmp_path / ".quality-runner" / "runs" / "sec-redaction-001").rglob("*")
        if path.is_file()
    ]
    assert all(secret not in text for text in artifact_texts)


def test_secret_like_source_evidence_is_redacted_across_generated_artifacts(tmp_path: Path) -> None:
    from quality_runner.handoff_lint import validate_slice_spec_content

    write_js_fixture(tmp_path)
    secret = "m7-shared-redaction-regression-secret-42"
    src = tmp_path / "src"
    src.mkdir()
    (src / "secrets.js").write_text(
        "\n".join(
            [
                (
                    f'const apiKey: string = "{secret}"; '
                    "const state = one ? two : three ? four : five;"
                ),
                f'const apiKey = "{secret}";',
                "const adjacent = one ? two : three ? four : five;",
                "const apiKey =",
                f'  "{secret}"; const multilineState = one ? two : three ? four : five;',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    payloads = {
        "inspect": inspect_payload(repo_root=tmp_path, run_id="shared-redaction-inspect"),
        "run": run_payload(repo_root=tmp_path, run_id="shared-redaction-run"),
        "verify": verify_gates_payload(
            repo_root=tmp_path,
            run_id="shared-redaction-verify",
            read_only_gates=True,
        ),
    }
    redacted_same_line = (
        'const apiKey: string = "<redacted>"; const state = one ? two : three ? four : five;'
    )
    redacted_multiline_finding = (
        '"<redacted>"; const multilineState = one ? two : three ? four : five;'
    )
    redacted_multiline_excerpt = (
        '  "<redacted>"; const multilineState = one ? two : three ? four : five;'
    )

    for payload in payloads.values():
        artifact_paths = payload["artifact_paths"]
        code_quality_scan = json.loads(
            Path(artifact_paths["code_quality_scan_json"]).read_text(encoding="utf-8")
        )
        for line, evidence in ((1, redacted_same_line), (5, redacted_multiline_finding)):
            finding = next(
                finding
                for finding in code_quality_scan["findings"]
                if finding["rule_id"] == "nested-ternary" and finding["line"] == line
            )
            expected_fingerprint = hashlib.sha256(
                f"nested-ternary:src/secrets.js:{evidence}".encode()
            ).hexdigest()[:16]

            assert finding["evidence"] == evidence
            assert finding["fingerprint"] == expected_fingerprint
        run_dir = Path(artifact_paths["code_quality_scan_json"]).parent
        artifact_texts = [
            path.read_text(encoding="utf-8") for path in run_dir.rglob("*") if path.is_file()
        ]
        assert all(secret not in text for text in artifact_texts)

    for name in ("run", "verify"):
        artifact_paths = payloads[name]["artifact_paths"]
        remediation_plan = json.loads(
            Path(artifact_paths["remediation_plan_json"]).read_text(encoding="utf-8")
        )
        adjacent_finding = next(
            finding
            for slice_item in remediation_plan["slices"]
            for finding in slice_item["findings"]
            if finding.get("rule_id") == "nested-ternary" and finding.get("line") == 3
        )
        excerpt = adjacent_finding["evidence_excerpt"]
        multiline_finding = next(
            finding
            for slice_item in remediation_plan["slices"]
            for finding in slice_item["findings"]
            if finding.get("rule_id") == "nested-ternary" and finding.get("line") == 5
        )
        slice_specs = list(
            Path(artifact_paths["remediation_plan_json"]).parent.glob("slice-specs/*.md")
        )

        assert 'const apiKey = "<redacted>";' in excerpt["context_before"]
        assert multiline_finding["evidence_excerpt"]["excerpt"] == redacted_multiline_excerpt
        assert slice_specs
        assert all(
            validate_slice_spec_content(path.read_text(encoding="utf-8"))["passed"]
            for path in slice_specs
        )


def test_secret_assignment_context_redacts_comments_and_expressions(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    secret = "m7-secret-assignment-context-regression-42"
    src = tmp_path / "src"
    src.mkdir()
    (src / "assignment-context-secrets.js").write_text(
        "\n".join(
            [
                (
                    "const apiKey /* compiler metadata */ = "
                    f'"{secret}"; const commentState = one ? two : three ? four : five;'
                ),
                (
                    f'const apiKey = String("{secret}"); '
                    "const expressionState = one ? two : three ? four : five;"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = run_payload(repo_root=tmp_path, run_id="assignment-context-redaction-001")
    code_quality_scan = json.loads(
        Path(payload["artifact_paths"]["code_quality_scan_json"]).read_text(encoding="utf-8")
    )
    expected_evidence = {
        1: (
            'const apiKey /* compiler metadata */ = "<redacted>"; '
            "const commentState = one ? two : three ? four : five;"
        ),
        2: (
            'const apiKey = String("<redacted>"); '
            "const expressionState = one ? two : three ? four : five;"
        ),
    }

    for line, evidence in expected_evidence.items():
        finding = next(
            item
            for item in code_quality_scan["findings"]
            if item["file"] == "src/assignment-context-secrets.js"
            and item["rule_id"] == "nested-ternary"
            and item["line"] == line
        )
        assert finding["evidence"] == evidence

    artifact_texts = [
        path.read_text(encoding="utf-8")
        for path in (
            tmp_path / ".quality-runner" / "runs" / "assignment-context-redaction-001"
        ).rglob("*")
        if path.is_file()
    ]
    assert all(secret not in text for text in artifact_texts)


def test_expensive_api_candidate_evidence_redacts_secret_like_source(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    secret = "m7-expensive-api-redaction-regression-secret-42"
    route = tmp_path / "app" / "api" / "chat" / "route.ts"
    route.parent.mkdir(parents=True)
    route.write_text(
        f'const apiKey = "{secret}"; await openai.chat.completions.create({{}});\n',
        encoding="utf-8",
    )

    payload = run_payload(
        repo_root=tmp_path, run_id="expensive-api-redaction-001", profile="default"
    )
    security_scan = json.loads(
        Path(payload["artifact_paths"]["security_scan_json"]).read_text(encoding="utf-8")
    )
    candidate = next(
        item for item in security_scan["candidates"] if item["category"] == "expensive-api-abuse"
    )
    expected_evidence = 'const apiKey = "<redacted>"; await openai.chat.completions.create({});'

    assert candidate["evidence"] == expected_evidence
    artifact_texts = [
        path.read_text(encoding="utf-8")
        for path in (tmp_path / ".quality-runner" / "runs" / "expensive-api-redaction-001").rglob(
            "*"
        )
        if path.is_file()
    ]
    assert all(secret not in text for text in artifact_texts)


def test_multiline_source_evidence_redacts_typed_and_concatenated_assignments(
    tmp_path: Path,
) -> None:
    from quality_runner.evidence_excerpts import read_line_excerpt

    write_js_fixture(tmp_path)
    secret = "m7-multiline-source-redaction-regression-secret-42"
    src = tmp_path / "src"
    src.mkdir()
    (src / "multiline-secrets.js").write_text(
        "\n".join(
            [
                "const apiKey: string =",
                f'  "{secret}"; const typedState = one ? two : three ? four : five;',
                "const concatKey =",
                '  "prefix" +',
                f'  "{secret}"; const concatState = one ? two : three ? four : five;',
                'const label = "safe"; const API_KEY: string = `',
                f"{secret}`; const templateState = one ? two : three ? four : five;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = run_payload(repo_root=tmp_path, run_id="multiline-redaction-001", profile="default")
    code_quality_scan = json.loads(
        Path(payload["artifact_paths"]["code_quality_scan_json"]).read_text(encoding="utf-8")
    )
    expected_evidence = {
        2: '"<redacted>"; const typedState = one ? two : three ? four : five;',
        5: '"<redacted>"; const concatState = one ? two : three ? four : five;',
        7: '"<redacted>"; const templateState = one ? two : three ? four : five;',
    }

    for line, evidence in expected_evidence.items():
        finding = next(
            item
            for item in code_quality_scan["findings"]
            if item["file"] == "src/multiline-secrets.js"
            and item["rule_id"] == "nested-ternary"
            and item["line"] == line
        )
        assert finding["evidence"] == evidence

    excerpt = read_line_excerpt(tmp_path, "src/multiline-secrets.js", 5)
    assert excerpt is not None
    assert (
        excerpt["excerpt"] == '  "<redacted>"; const concatState = one ? two : three ? four : five;'
    )
    artifact_texts = [
        path.read_text(encoding="utf-8")
        for path in (tmp_path / ".quality-runner" / "runs" / "multiline-redaction-001").rglob("*")
        if path.is_file()
    ]
    assert all(secret not in text for text in artifact_texts)


def test_expensive_api_candidate_evidence_redacts_multiline_template_secret(
    tmp_path: Path,
) -> None:
    write_js_fixture(tmp_path)
    secret = "m7-template-expensive-api-redaction-regression-secret-42"
    route = tmp_path / "app" / "api" / "chat" / "route.ts"
    route.parent.mkdir(parents=True)
    route.write_text(
        "\n".join(
            [
                'const label = "safe"; const API_KEY: string = `',
                f"{secret}`; await openai.chat.completions.create({{}});",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = run_payload(
        repo_root=tmp_path,
        run_id="template-expensive-api-redaction-001",
        profile="default",
    )
    security_scan = json.loads(
        Path(payload["artifact_paths"]["security_scan_json"]).read_text(encoding="utf-8")
    )
    candidate = next(
        item for item in security_scan["candidates"] if item["category"] == "expensive-api-abuse"
    )

    assert candidate["evidence"] == '"<redacted>"; await openai.chat.completions.create({});'
    artifact_texts = [
        path.read_text(encoding="utf-8")
        for path in (
            tmp_path / ".quality-runner" / "runs" / "template-expensive-api-redaction-001"
        ).rglob("*")
        if path.is_file()
    ]
    assert all(secret not in text for text in artifact_texts)


def test_expensive_api_candidate_evidence_redacts_multiline_secret_like_source(
    tmp_path: Path,
) -> None:
    write_js_fixture(tmp_path)
    secret = "m7-multiline-expensive-api-redaction-regression-secret-42"
    route = tmp_path / "app" / "api" / "chat" / "route.ts"
    route.parent.mkdir(parents=True)
    route.write_text(
        "\n".join(
            [
                "const apiKey =",
                f'  "{secret}"; await openai.chat.completions.create({{}});',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = run_payload(
        repo_root=tmp_path,
        run_id="multiline-expensive-api-redaction-001",
        profile="default",
    )
    security_scan = json.loads(
        Path(payload["artifact_paths"]["security_scan_json"]).read_text(encoding="utf-8")
    )
    candidate = next(
        item for item in security_scan["candidates"] if item["category"] == "expensive-api-abuse"
    )

    assert candidate["evidence"] == '"<redacted>"; await openai.chat.completions.create({});'
    artifact_texts = [
        path.read_text(encoding="utf-8")
        for path in (
            tmp_path / ".quality-runner" / "runs" / "multiline-expensive-api-redaction-001"
        ).rglob("*")
        if path.is_file()
    ]
    assert all(secret not in text for text in artifact_texts)


def test_agent_review_gate_for_api_routes(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    api_dir = tmp_path / "app" / "api" / "users"
    api_dir.mkdir(parents=True)
    (api_dir / "route.ts").write_text(
        "export async function GET() { return Response.json({ ok: true }); }\n",
        encoding="utf-8",
    )
    security_scan = _run_scan(tmp_path)
    gate_ids = {gate["id"] for gate in security_scan["agent_review_gates"]}
    assert "security_api_route_auth_review" in gate_ids


def test_agent_review_gate_for_webhook_without_signature(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    webhook_dir = tmp_path / "app" / "api" / "webhook"
    webhook_dir.mkdir(parents=True)
    (webhook_dir / "route.ts").write_text(
        "export async function POST(req) { return Response.json({ ok: true }); }\n",
        encoding="utf-8",
    )
    security_scan = _run_scan(tmp_path)
    gate_ids = {gate["id"] for gate in security_scan["agent_review_gates"]}
    assert "security_webhook_signature_review" in gate_ids


def test_run_payload_writes_security_scan_json(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    payload = run_payload(repo_root=tmp_path, run_id="sec-run-001", profile="default")
    artifact_paths = payload["artifact_paths"]
    assert "security_scan_json" in artifact_paths
    security_scan = json.loads(
        Path(artifact_paths["security_scan_json"]).read_text(encoding="utf-8")
    )
    assert security_scan["schema"] == "quality-runner-security-scan-v0.1"


def test_security_findings_in_quality_audit(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner.security]",
                'required_capabilities = ["security_dependency_audit"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    api_dir = tmp_path / "pages" / "api" / "hello"
    api_dir.mkdir(parents=True)
    (api_dir / "index.ts").write_text("export default function handler() {}\n", encoding="utf-8")
    payload = run_payload(repo_root=tmp_path, run_id="sec-audit-001", profile="default")
    audit = json.loads(
        Path(payload["artifact_paths"]["quality_audit_json"]).read_text(encoding="utf-8")
    )
    categories = {finding["category"] for finding in audit["findings"]}
    assert any(category.startswith("security:") for category in categories)


def test_security_review_in_handoff_markdown(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    api_dir = tmp_path / "app" / "api" / "health"
    api_dir.mkdir(parents=True)
    (api_dir / "route.ts").write_text(
        "export async function GET() { return Response.json({}); }\n", encoding="utf-8"
    )
    payload = run_payload(repo_root=tmp_path, run_id="sec-handoff-001", profile="default")
    handoff_md = Path(payload["artifact_paths"]["agent_handoff_md"]).read_text(encoding="utf-8")
    assert "## Security Review Gates" in handoff_md
    assert "security_api_route_auth_review" in handoff_md


def test_security_review_in_handoff_json(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    api_dir = tmp_path / "src" / "routes"
    api_dir.mkdir(parents=True)
    (api_dir / "api.ts").write_text("export const routes = [];\n", encoding="utf-8")
    payload = run_payload(repo_root=tmp_path, run_id="sec-handoff-json", profile="default")
    handoff = json.loads(
        Path(payload["artifact_paths"]["agent_handoff_json"]).read_text(encoding="utf-8")
    )
    security_review = handoff.get("security_review")
    assert isinstance(security_review, dict)
    assert "agent_review_gates" in security_review


def test_remediation_plan_prioritizes_security(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "bad.js").write_text(
        'const token = "example-placeholder-not-a-real-token";\n', encoding="utf-8"
    )
    payload = run_payload(repo_root=tmp_path, run_id="sec-plan-001", profile="default")
    plan = json.loads(
        Path(payload["artifact_paths"]["remediation_plan_json"]).read_text(encoding="utf-8")
    )
    slices = plan["slices"]
    assert slices
    first_categories = {finding["category"] for finding in slices[0]["findings"]}
    assert any(category.startswith("security:") for category in first_categories)
    security_review_slices = plan.get("security_review_slices", [])
    assert isinstance(security_review_slices, list)


def test_resolution_ledger_security_fingerprint_stable(tmp_path: Path) -> None:
    first = security_candidate_fingerprint(
        category="secrets-exposure",
        file="src/a.js",
        line=3,
        evidence='apiKey = "abc"',
    )
    second = security_candidate_fingerprint(
        category="secrets-exposure",
        file="src/a.js",
        line=3,
        evidence='apiKey = "abc"',
    )
    assert first == second
    assert first.startswith("sec-")


def test_resolution_ledger_includes_security_entries(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "bad.js").write_text("eval(input)\n", encoding="utf-8")
    payload = run_payload(repo_root=tmp_path, run_id="sec-ledger-001", profile="default")
    ledger = json.loads(
        Path(payload["artifact_paths"]["resolution_ledger_json"]).read_text(encoding="utf-8")
    )
    security_entries = [
        entry for entry in ledger["entries"] if entry.get("ledger_kind") == "security"
    ]
    assert security_entries
    assert security_entries[0]["status"] in {"unreviewed", "review-required"}


def test_config_disabling_security_rules(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner.security]",
                "enabled = true",
                'disabled_rule_groups = ["dangerous-sink"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "bad.js").write_text("eval(x)\n", encoding="utf-8")
    security_scan = _run_scan(tmp_path)
    categories = {item["category"] for item in security_scan["candidates"]}
    assert "dangerous-sink" not in categories


def test_config_disabling_security_entirely(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    config = load_repo_config(tmp_path)
    config["security"] = {"enabled": False}
    settings = security_settings(config)
    assert settings["enabled"] is False


def test_inspect_payload_writes_security_scan_without_source_edits(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    source = tmp_path / "src" / "app.js"
    source.parent.mkdir(parents=True)
    source.write_text("console.log('baseline')\n", encoding="utf-8")
    before = source.read_text(encoding="utf-8")
    payload = inspect_payload(repo_root=tmp_path, run_id="sec-inspect-001", profile="default")
    assert Path(payload["artifact_paths"]["security_scan_json"]).exists()
    assert source.read_text(encoding="utf-8") == before
    run_dir = tmp_path / ".quality-runner" / "runs" / "sec-inspect-001"
    assert run_dir.exists()
    assert (run_dir / "security-scan.json").exists()


def test_capability_matrix_includes_security_summary(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    payload = inspect_payload(repo_root=tmp_path, run_id="sec-cap-001", profile="default")
    matrix = json.loads(
        Path(payload["artifact_paths"]["capability_matrix_json"]).read_text(encoding="utf-8")
    )
    assert "security_summary" in matrix


def test_merge_security_into_capability_map_adds_agent_review(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    api_dir = tmp_path / "app" / "api" / "items"
    api_dir.mkdir(parents=True)
    (api_dir / "route.ts").write_text("export async function GET() {}\n", encoding="utf-8")
    security_scan = _run_scan(tmp_path)
    merged = merge_security_into_capability_map(
        {
            "schema": "quality-runner-capability-map-v0.1",
            "available": [],
            "missing": [],
            "warnings": [],
        },
        security_scan,
    )
    kinds = {item.get("capability_kind") for item in merged["available"]}
    assert "agent_review" in kinds
