from __future__ import annotations

from pathlib import Path

from quality_runner.schema_constants import SKILL_REVIEW_REPORT_SCHEMA


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _skills_enabled_config(
    *,
    active: list[str] | None = None,
    local: list[dict[str, object]] | None = None,
) -> dict:
    section: dict = {"enabled": True}
    if active is not None:
        section["active"] = active
    if local is not None:
        section["local"] = local
    return {"skills": section}


def _clickable_div_skill_toml() -> str:
    return """
id = "ui-polish"
name = "UI Polish Standards"
version = "0.1.0"
description = "UI polish checks."

[[deterministic_rules]]
id = "ui-clickable-div"
type = "disallowed_pattern"
category = "accessibility"
severity = "warning"
paths = ["**/*.tsx", "**/*.jsx"]
disallowed_patterns = ["<div[^>]+onClick="]
message = "Clickable divs should usually be semantic buttons or links."
risk = "Non-semantic interactive elements hurt keyboard and assistive technology users."
expected = "Use button/link semantics or provide keyboard and ARIA support."
verification = "Rerun quality-runner and confirm this skill finding clears."
""".strip()


def _empty_state_skill_toml() -> str:
    return """
id = "ui-polish"
name = "UI Polish Standards"

[[deterministic_rules]]
id = "ui-empty-state-required"
type = "trigger_without_required"
category = "ui"
severity = "warning"
paths = ["**/*.tsx", "**/*.jsx"]
trigger_patterns = ["\\\\.map\\\\(", "useQuery\\\\(", "fetch\\\\("]
required_patterns = ["EmptyState", "empty", "No results", "No items"]
message = "Data-driven UI should include an empty state."
risk = "Users may see blank or confusing screens when data is unavailable."
expected = "Add a clear empty state near the data-rendering branch."
verification = "Rerun quality-runner and confirm this skill finding clears."
""".strip()


def _import_boundary_skill_toml() -> str:
    return """
id = "architecture-boundaries"
name = "Architecture Boundaries"

[[deterministic_rules]]
id = "ui-no-server-imports"
type = "import_boundary"
category = "architecture"
severity = "warning"
paths = ["apps/web/**", "packages/ui/**"]
disallowed_imports = ["server/**", "packages/server/**", "packages/domain/**"]
allowed_imports = ["packages/domain/types/**"]
message = "UI code should not import server or domain internals directly."
risk = "Cross-layer imports couple presentation code to implementation details."
expected = "Move access behind API/client/service boundaries or import only stable shared types."
verification = "Rerun quality-runner and confirm this skill finding clears."
""".strip()


def _agent_review_skill_toml() -> str:
    return '''
id = "ui-polish"
name = "UI Polish Standards"

[[agent_reviews]]
id = "ui-polish-review"
category = "ui"
severity = "observation"
paths = ["apps/web/**"]
focus = ["loading states", "empty states"]
rubric = """
Review UI-facing components for product polish.
Only create findings with concrete file/line evidence.
"""
'''.strip()


def _ui_foundations_skill_toml() -> str:
    return (Path(__file__).parents[1] / "docs/examples/ui-foundations.toml").read_text(
        encoding="utf-8"
    )


def _test_strategy_skill_toml() -> str:
    return (Path(__file__).parents[1] / "docs/examples/test-strategy.toml").read_text(
        encoding="utf-8"
    )


def _security_privacy_skill_toml() -> str:
    return (Path(__file__).parents[1] / "docs/examples/security-privacy.toml").read_text(
        encoding="utf-8"
    )


def _release_readiness_skill_toml() -> str:
    return (Path(__file__).parents[1] / "docs/examples/release-readiness.toml").read_text(
        encoding="utf-8"
    )


def _pr_risk_skill_toml() -> str:
    return (Path(__file__).parents[1] / "docs/examples/pr-risk.toml").read_text(encoding="utf-8")


def _install_skill(tmp_path: Path, skill_id: str, content: str) -> str:
    relative = f".quality-runner/skills/{skill_id}.toml"
    _write(tmp_path / relative, content)
    return relative


def test_quality_skills_disabled_by_default(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _install_skill(tmp_path, "ui-polish", _clickable_div_skill_toml())
    _write(tmp_path / "apps/web/page.tsx", "<div onClick={onOpen}>Open</div>\n")

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    assert not any(str(finding["category"]).startswith("skill:") for finding in result["findings"])


def test_quality_skill_disallowed_pattern_detects_line(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_path = _install_skill(tmp_path, "ui-polish", _clickable_div_skill_toml())
    _write(tmp_path / "apps/web/page.tsx", "<div onClick={onOpen}>Open</div>\n")
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path, "applies_to": ["apps/web/**"]}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config=config)
    matches = [
        finding
        for finding in result["findings"]
        if finding["rule_id"] == "ui-polish/ui-clickable-div"
    ]
    assert len(matches) == 1
    finding = matches[0]
    assert finding["file"] == "apps/web/page.tsx"
    assert finding["line"] == 1
    assert "onClick" in finding["evidence"]
    assert "assistive technology" in finding["risk"]
    assert "button/link" in finding["expected_improvement"]


def test_ui_foundations_pack_reports_source_findings_and_review_scopes(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import build_skill_review_packet

    skill_path = _install_skill(tmp_path, "ui-foundations", _ui_foundations_skill_toml())
    component = (
        "export function Results({ items }) {\n"
        "  const response = fetch('/api/results');\n"
        "  return items.map((item) => <div key={item.id}>{item.name}</div>);\n"
        "}\n"
    )
    styles = (
        ".hero { background-clip: text; border-radius: 40px; "
        "background: repeating-linear-gradient(90deg, #fff, #fff 1px, #eee 1px, #eee 2px); }\n"
    )
    _write(tmp_path / "src/components/Results.tsx", component)
    _write(tmp_path / "src/components/Results.css", styles)
    config = _skills_enabled_config(
        active=["ui-foundations"],
        local=[
            {
                "id": "ui-foundations",
                "path": skill_path,
                "applies_to": ["src/**"],
            }
        ],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "ui-foundations"}, config=config)
    rule_ids = {str(finding["rule_id"]) for finding in result["findings"]}
    assert "ui-foundations/gradient-text" in rule_ids
    assert "ui-foundations/decorative-gradient-stripes" in rule_ids
    assert "ui-foundations/oversized-corner-radius" in rule_ids
    assert "ui-foundations/collection-empty-state" in rule_ids
    assert "ui-foundations/async-loading-state" in rule_ids
    assert result["quality_skills"][0]["id"] == "ui-foundations"
    deterministic_coverage = [
        item for item in result["skill_coverage"] if item["rule_type"] != "agent_review"
    ]
    assert all(item["status"] in {"matched", "evaluated"} for item in deterministic_coverage)

    reviewed = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "ui-foundations-reviewed"},
        config=config,
        skill_review_report={
            "schema": SKILL_REVIEW_REPORT_SCHEMA,
            "run_id": "ui-foundations-reviewed",
            "findings": [
                {
                    "skill_id": "ui-foundations",
                    "review_id": "visual-hierarchy",
                    "rule_id": "visual-hierarchy/competing-actions",
                    "severity": "observation",
                    "confidence": "low",
                    "file": "src/components/Results.tsx",
                    "line": 2,
                    "summary": "The collection render does not make a primary action hierarchy evident.",
                    "evidence": "return items.map((item) => <div key={item.id}>{item.name}</div>);",
                    "risk": "Users may not know which action or destination is most important.",
                    "expected_improvement": "Make the intended primary action explicit near the collection output.",
                    "verification": "Rerun quality-runner and review the resulting UI state.",
                }
            ],
        },
    )
    assert any(
        finding["rule_id"] == "visual-hierarchy/competing-actions"
        for finding in reviewed["findings"]
    )

    skills, warnings = load_active_skills(tmp_path, config)
    assert warnings == []
    packet = build_skill_review_packet(
        run_id="ui-foundations",
        repo_root=tmp_path,
        scanned_files=[
            {"path": "src/components/Results.tsx", "lines": component.splitlines()},
            {"path": "src/components/Results.css", "lines": styles.splitlines()},
        ],
        skills=skills,
    )
    assert packet is not None
    assert len(packet["reviews"]) == 4
    assert {review["review_id"] for review in packet["reviews"]} == {
        "visual-hierarchy",
        "states-and-interactions",
        "accessibility-foundations",
        "visual-restraint-and-system-fit",
    }
    assert len(packet["included_files"]) == 2


def test_test_strategy_pack_reports_source_findings_and_review_scopes(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import build_skill_review_packet

    skill_path = _install_skill(tmp_path, "test-strategy", _test_strategy_skill_toml())
    test_source = (
        'describe("results", () => {\n'
        '  test.skip("pending regression", () => {\n'
        "    runScenario();\n"
        "  });\n"
        "});\n"
    )
    service_source = "export function loadResults() { return fetch('/api/results'); }\n"
    _write(tmp_path / "tests/results.test.ts", test_source)
    _write(tmp_path / "src/results.ts", service_source)
    config = _skills_enabled_config(
        active=["test-strategy"],
        local=[
            {
                "id": "test-strategy",
                "path": skill_path,
                "applies_to": ["src/**", "tests/**"],
            }
        ],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "test-strategy"}, config=config)
    rule_ids = {str(finding["rule_id"]) for finding in result["findings"]}
    assert "test-strategy/skipped-or-focused-test" in rule_ids
    assert "test-strategy/test-file-without-visible-assertion" in rule_ids
    assert result["quality_skills"][0]["id"] == "test-strategy"

    reviewed = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "test-strategy-reviewed"},
        config=config,
        skill_review_report={
            "schema": SKILL_REVIEW_REPORT_SCHEMA,
            "run_id": "test-strategy-reviewed",
            "findings": [
                {
                    "skill_id": "test-strategy",
                    "review_id": "behavior-and-contract-coverage",
                    "rule_id": "behavior-and-contract-coverage/missing-error-case",
                    "severity": "observation",
                    "confidence": "low",
                    "file": "src/results.ts",
                    "line": 1,
                    "summary": "The data-loading contract has no visible test for a failed request.",
                    "evidence": "export function loadResults() { return fetch('/api/results'); }",
                    "risk": "A request failure could regress without a test protecting the error behavior.",
                    "expected_improvement": "Add a regression test for the failed-request behavior and its user-visible outcome.",
                    "verification": "Rerun quality-runner and the repository test command after adding the regression case.",
                }
            ],
        },
    )
    assert any(
        finding["rule_id"] == "behavior-and-contract-coverage/missing-error-case"
        for finding in reviewed["findings"]
    )

    skills, warnings = load_active_skills(tmp_path, config)
    assert warnings == []
    packet = build_skill_review_packet(
        run_id="test-strategy",
        repo_root=tmp_path,
        scanned_files=[
            {"path": "tests/results.test.ts", "lines": test_source.splitlines()},
            {"path": "src/results.ts", "lines": service_source.splitlines()},
        ],
        skills=skills,
    )
    assert packet is not None
    assert len(packet["reviews"]) == 4
    assert {review["review_id"] for review in packet["reviews"]} == {
        "behavior-and-contract-coverage",
        "regression-value",
        "isolation-and-determinism",
        "quality-gates-and-evidence",
    }
    assert len(packet["included_files"]) == 2


def test_security_privacy_pack_reports_safe_source_findings_and_review_scopes(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import build_skill_review_packet

    skill_path = _install_skill(tmp_path, "security-privacy", _security_privacy_skill_toml())
    source = (
        "def fetch_profile(url):\n"
        "    response = requests.get(url, verify=False)\n"
        "    cors = {'origin': '*'}\n"
        "    return response.json(), cors\n"
    )
    _write(tmp_path / "src/api.py", source)
    config = _skills_enabled_config(
        active=["security-privacy"],
        local=[
            {
                "id": "security-privacy",
                "path": skill_path,
                "applies_to": ["src/**"],
            }
        ],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "security-privacy"}, config=config)
    rule_ids = {str(finding["rule_id"]) for finding in result["findings"]}
    assert "security-privacy/disabled-tls-verification" in rule_ids
    assert "security-privacy/wildcard-cors-origin" in rule_ids
    assert result["quality_skills"][0]["id"] == "security-privacy"
    assert all(
        "requests.get" not in str(finding["evidence"]) or "verify=False" in str(finding["evidence"])
        for finding in result["findings"]
        if str(finding["rule_id"]).startswith("security-privacy/")
    )

    reviewed = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "security-privacy-reviewed"},
        config=config,
        skill_review_report={
            "schema": SKILL_REVIEW_REPORT_SCHEMA,
            "run_id": "security-privacy-reviewed",
            "findings": [
                {
                    "skill_id": "security-privacy",
                    "review_id": "auth-and-authorization",
                    "rule_id": "auth-and-authorization/missing-resource-guard",
                    "severity": "observation",
                    "confidence": "low",
                    "file": "src/api.py",
                    "line": 1,
                    "summary": "The profile-fetching boundary has no visible resource authorization check.",
                    "evidence": "def fetch_profile(url):",
                    "risk": "A caller may reach a sensitive resource without an object-level authorization decision.",
                    "expected_improvement": "Add or cite the authorization guard and resource-scope check before the external request.",
                    "verification": "Rerun quality-runner and the security-focused test command after confirming the guard.",
                }
            ],
        },
    )
    assert any(
        finding["rule_id"] == "auth-and-authorization/missing-resource-guard"
        for finding in reviewed["findings"]
    )

    skills, warnings = load_active_skills(tmp_path, config)
    assert warnings == []
    packet = build_skill_review_packet(
        run_id="security-privacy",
        repo_root=tmp_path,
        scanned_files=[{"path": "src/api.py", "lines": source.splitlines()}],
        skills=skills,
    )
    assert packet is not None
    assert len(packet["reviews"]) == 5
    assert {review["review_id"] for review in packet["reviews"]} == {
        "secrets-and-redaction",
        "auth-and-authorization",
        "privacy-and-data-flow",
        "input-and-boundary-security",
        "security-evidence-and-gates",
    }
    assert len(packet["included_files"]) == 1


def test_release_readiness_pack_reports_release_signals_and_review_scopes(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import build_skill_review_packet

    skill_path = _install_skill(tmp_path, "release-readiness", _release_readiness_skill_toml())
    release_workflow = (
        "name: release\n"
        "jobs:\n"
        "  release:\n"
        "    steps:\n"
        "      - run: uv publish\n"
        "      - continue-on-error: true\n"
    )
    source = "export function releaseArtifact() { return publishArtifact(); }\n"
    _write(tmp_path / "config/release.yml", release_workflow)
    _write(tmp_path / "src/release.ts", source)
    config = _skills_enabled_config(
        active=["release-readiness"],
        local=[{"id": "release-readiness", "path": skill_path}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "release-readiness"}, config=config)
    rule_ids = {str(finding["rule_id"]) for finding in result["findings"]}
    assert "release-readiness/verification-bypass" in rule_ids
    assert "release-readiness/release-job-without-quality-command" in rule_ids
    assert result["quality_skills"][0]["id"] == "release-readiness"

    reviewed = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "release-readiness-reviewed"},
        config=config,
        skill_review_report={
            "schema": SKILL_REVIEW_REPORT_SCHEMA,
            "run_id": "release-readiness-reviewed",
            "findings": [
                {
                    "skill_id": "release-readiness",
                    "review_id": "release-evidence",
                    "rule_id": "release-evidence/missing-build-proof",
                    "severity": "observation",
                    "confidence": "low",
                    "file": "config/release.yml",
                    "line": 1,
                    "summary": "The release workflow does not show build or test evidence before publication.",
                    "evidence": "name: release",
                    "risk": "The published artifact may not be verified by the repository's quality path.",
                    "expected_improvement": "Add or cite the build and test gates that must pass before publication.",
                    "verification": "Rerun quality-runner and the release verification workflow after adding the evidence.",
                }
            ],
        },
    )
    assert any(
        finding["rule_id"] == "release-evidence/missing-build-proof"
        for finding in reviewed["findings"]
    )

    skills, warnings = load_active_skills(tmp_path, config)
    assert warnings == []
    packet = build_skill_review_packet(
        run_id="release-readiness",
        repo_root=tmp_path,
        scanned_files=[
            {"path": "config/release.yml", "lines": release_workflow.splitlines()},
            {"path": "src/release.ts", "lines": source.splitlines()},
        ],
        skills=skills,
    )
    assert packet is not None
    assert len(packet["reviews"]) == 5
    assert {review["review_id"] for review in packet["reviews"]} == {
        "release-evidence",
        "ship-blockers-and-quality-ladder",
        "compatibility-and-change-surface",
        "rollback-and-operations",
        "handoff-and-communication",
    }
    assert len(packet["included_files"]) == 2


def test_pr_risk_pack_reports_merge_integrity_and_review_scopes(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import build_skill_review_packet

    skill_path = _install_skill(tmp_path, "pr-risk", _pr_risk_skill_toml())
    source = "<<<<<<< HEAD\nexport function feature() { return 'old'; }\n>>>>>>> feature-branch\n"
    _write(tmp_path / "src/feature.ts", source)
    config = _skills_enabled_config(
        active=["pr-risk"],
        local=[{"id": "pr-risk", "path": skill_path}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "pr-risk"}, config=config)
    rule_ids = {str(finding["rule_id"]) for finding in result["findings"]}
    assert "pr-risk/merge-conflict-marker" in rule_ids
    assert result["quality_skills"][0]["id"] == "pr-risk"

    reviewed = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "pr-risk-reviewed"},
        config=config,
        skill_review_report={
            "schema": SKILL_REVIEW_REPORT_SCHEMA,
            "run_id": "pr-risk-reviewed",
            "findings": [
                {
                    "skill_id": "pr-risk",
                    "review_id": "contract-and-regression-risk",
                    "rule_id": "contract-and-regression-risk/missing-regression-test",
                    "severity": "observation",
                    "confidence": "low",
                    "file": "src/feature.ts",
                    "line": 2,
                    "summary": "The changed feature has no visible regression test for its returned behavior.",
                    "evidence": "export function feature() { return 'old'; }",
                    "risk": "A contract change could merge without a test that protects the expected behavior.",
                    "expected_improvement": "Add or cite a regression test for the feature's public behavior.",
                    "verification": "Rerun quality-runner and the focused test command after adding the regression coverage.",
                }
            ],
        },
    )
    assert any(
        finding["rule_id"] == "contract-and-regression-risk/missing-regression-test"
        for finding in reviewed["findings"]
    )

    skills, warnings = load_active_skills(tmp_path, config)
    assert warnings == []
    packet = build_skill_review_packet(
        run_id="pr-risk",
        repo_root=tmp_path,
        scanned_files=[{"path": "src/feature.ts", "lines": source.splitlines()}],
        skills=skills,
    )
    assert packet is not None
    assert len(packet["reviews"]) == 5
    assert {review["review_id"] for review in packet["reviews"]} == {
        "changed-surface-map",
        "contract-and-regression-risk",
        "scope-and-cohesion",
        "merge-evidence",
        "handoff-and-remediation",
    }
    assert len(packet["included_files"]) == 1


def test_quality_skill_surfaces_rule_metadata_confidence_and_coverage(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_content = _clickable_div_skill_toml().replace(
        'severity = "warning"', 'severity = "observation"\nconfidence = "low"'
    )
    skill_path = _install_skill(tmp_path, "ui-polish", skill_content)
    _write(tmp_path / "apps/web/page.tsx", "<div onClick={onOpen}>Open</div>\n")
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path, "applies_to": ["apps/web/**"]}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config=config)

    finding = next(
        finding
        for finding in result["findings"]
        if finding["rule_id"] == "ui-polish/ui-clickable-div"
    )
    assert finding["confidence"] == "low"
    assert finding["rule_category"] == "accessibility"
    assert finding["rule_message"] == "Clickable divs should usually be semantic buttons or links."
    coverage = result["skill_coverage"][0]
    assert coverage["status"] == "matched"
    assert coverage["scoped_files"] == 1
    assert coverage["matched_files"] == 1
    assert coverage["finding_count"] == 1
    assert coverage["confidence"] == "low"
    assert result["quality_skills"][0]["version"] == "0.1.0"
    assert len(result["quality_skills"][0]["content_sha256"]) == 64


def test_quality_skill_coverage_reports_invalid_pattern_skip(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_content = _clickable_div_skill_toml().replace(
        'disallowed_patterns = ["<div[^>]+onClick="]', 'disallowed_patterns = ["["]'
    )
    skill_path = _install_skill(tmp_path, "ui-polish", skill_content)
    _write(tmp_path / "apps/web/page.tsx", "<div onClick={onOpen}>Open</div>\n")
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config=config)

    coverage = result["skill_coverage"][0]
    assert coverage["status"] == "skipped"
    assert coverage["skipped_reason"] == "all configured disallowed_patterns are invalid regexes"
    assert coverage["finding_count"] == 0


def test_quality_skill_ingest_surfaces_skipped_rule_warning(tmp_path: Path) -> None:
    from quality_runner.skill_ingest import ingest_skill_pack

    candidate = tmp_path / "candidate.toml"
    candidate.write_text(
        """
id = "ui-polish"
name = "UI Polish Standards"

[[deterministic_rules]]
id = "missing-message"
type = "disallowed_pattern"
paths = ["**/*.tsx"]
""".strip(),
        encoding="utf-8",
    )

    result = ingest_skill_pack(
        candidate,
        skill_id="ui-polish",
        repo_root=tmp_path,
        write=False,
    )

    assert result["status"] == "validated"
    assert any("deterministic_rules[0]" in warning for warning in result["warnings"])


def test_quality_skill_trigger_without_required_detects_missing_empty_state(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_path = _install_skill(tmp_path, "ui-polish", _empty_state_skill_toml())
    _write(
        tmp_path / "apps/web/page.tsx",
        "export function Page({ items }) {\n  return items.map((item) => <div key={item.id} />);\n}\n",
    )
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config=config)
    matches = [
        finding
        for finding in result["findings"]
        if finding["rule_id"] == "ui-polish/ui-empty-state-required"
    ]
    assert len(matches) == 1
    assert matches[0]["line"] == 2


def test_quality_skill_trigger_without_required_passes_when_required_text_exists(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_path = _install_skill(tmp_path, "ui-polish", _empty_state_skill_toml())
    _write(
        tmp_path / "apps/web/page.tsx",
        "export function Page({ items }) {\n"
        "  if (!items.length) return <EmptyState />;\n"
        "  return items.map((item) => <div key={item.id} />);\n"
        "}\n",
    )
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config=config)
    assert not any(
        finding["rule_id"] == "ui-polish/ui-empty-state-required" for finding in result["findings"]
    )


def test_quality_skill_import_boundary_detects_forbidden_import(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_path = _install_skill(tmp_path, "architecture-boundaries", _import_boundary_skill_toml())
    _write(tmp_path / "apps/web/page.tsx", 'import db from "../../server/db";\n')
    _write(tmp_path / "server/db.ts", "export const db = {};\n")
    config = _skills_enabled_config(
        active=["architecture-boundaries"],
        local=[{"id": "architecture-boundaries", "path": skill_path}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config=config)
    matches = [
        finding
        for finding in result["findings"]
        if finding["rule_id"] == "architecture-boundaries/ui-no-server-imports"
    ]
    assert len(matches) == 1
    assert matches[0]["file"] == "apps/web/page.tsx"


def test_quality_skill_import_boundary_respects_allowed_imports(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_path = _install_skill(tmp_path, "architecture-boundaries", _import_boundary_skill_toml())
    _write(
        tmp_path / "apps/web/page.tsx",
        'import type { User } from "../../packages/domain/types/user";\n',
    )
    config = _skills_enabled_config(
        active=["architecture-boundaries"],
        local=[{"id": "architecture-boundaries", "path": skill_path}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config=config)
    assert not any(
        finding["rule_id"] == "architecture-boundaries/ui-no-server-imports"
        for finding in result["findings"]
    )


def test_quality_skill_only_active_skills_run(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    ui_path = _install_skill(tmp_path, "ui-polish", _clickable_div_skill_toml())
    arch_path = _install_skill(tmp_path, "architecture-boundaries", _import_boundary_skill_toml())
    _write(tmp_path / "apps/web/page.tsx", "<div onClick={onOpen}>Open</div>\n")
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[
            {"id": "ui-polish", "path": ui_path},
            {"id": "architecture-boundaries", "path": arch_path},
        ],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config=config)
    rule_ids = {finding["rule_id"] for finding in result["findings"]}
    assert "ui-polish/ui-clickable-div" in rule_ids
    assert "architecture-boundaries/ui-no-server-imports" not in rule_ids


def test_quality_skill_malformed_file_does_not_crash(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_path = ".quality-runner/skills/ui-polish.toml"
    _write(tmp_path / skill_path, "this is not valid [[[\n")
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config=config)
    assert result["summary"]["total_findings"] >= 0


def test_quality_skill_findings_are_deterministic(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_path = _install_skill(tmp_path, "ui-polish", _clickable_div_skill_toml())
    _write(tmp_path / "apps/web/a.tsx", "<div onClick={a}>A</div>\n")
    _write(tmp_path / "apps/web/b.tsx", "<div onClick={b}>B</div>\n")
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path}],
    )

    first = create_code_quality_scan(tmp_path, scan={"run_id": "first"}, config=config)
    second = create_code_quality_scan(tmp_path, scan={"run_id": "second"}, config=config)
    first_keys = [(item["file"], item["line"], item["rule_id"]) for item in first["findings"]]
    second_keys = [(item["file"], item["line"], item["rule_id"]) for item in second["findings"]]
    assert first_keys == second_keys


def test_skill_review_packet_contains_active_review_rubrics(tmp_path: Path) -> None:
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import build_skill_review_packet

    skill_path = _install_skill(tmp_path, "ui-polish", _agent_review_skill_toml())
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path}],
    )
    skills, _warnings = load_active_skills(tmp_path, config)
    packet = build_skill_review_packet(
        run_id="run-001",
        repo_root=tmp_path,
        scanned_files=[{"path": "apps/web/page.tsx", "lines": ["export const Page = () => null;"]}],
        skills=skills,
    )

    assert packet is not None
    assert packet["active_skill_ids"] == ["ui-polish"]
    assert packet["output_schema"] == SKILL_REVIEW_REPORT_SCHEMA
    reviews = packet["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["skill_id"] == "ui-polish"
    assert reviews[0]["review_id"] == "ui-polish-review"
    assert "product polish" in reviews[0]["rubric"]
    assert packet["review_policy"] == {
        "recall_preference": "high",
        "allow_low_confidence": True,
        "require_file_line_evidence": True,
        "do_not_invent_evidence": True,
    }


def test_skill_review_report_validation_rejects_missing_evidence(tmp_path: Path) -> None:
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import validate_skill_review_report

    skill_path = _install_skill(tmp_path, "ui-polish", _agent_review_skill_toml())
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path}],
    )
    skills, _warnings = load_active_skills(tmp_path, config)
    report = {
        "schema": SKILL_REVIEW_REPORT_SCHEMA,
        "run_id": "run-001",
        "findings": [
            {
                "skill_id": "ui-polish",
                "review_id": "ui-polish-review",
                "rule_id": "ui-polish-review/missing-empty-state",
                "severity": "observation",
                "confidence": "medium",
                "file": "apps/web/page.tsx",
                "line": 1,
                "summary": "Missing empty state.",
                "risk": "Users may see a blank screen.",
                "expected_improvement": "Add an empty state.",
                "verification": "Rerun quality-runner.",
            }
        ],
    }

    result = validate_skill_review_report(report, skills=skills, repo_root=tmp_path)
    assert result["accepted_count"] == 0
    assert result["rejected_count"] == 1


def test_skill_review_report_validation_rejects_missing_file_or_line(tmp_path: Path) -> None:
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import validate_skill_review_report

    skill_path = _install_skill(tmp_path, "ui-polish", _agent_review_skill_toml())
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path}],
    )
    skills, _warnings = load_active_skills(tmp_path, config)
    report = {
        "schema": SKILL_REVIEW_REPORT_SCHEMA,
        "run_id": "run-001",
        "findings": [
            {
                "skill_id": "ui-polish",
                "review_id": "ui-polish-review",
                "severity": "observation",
                "confidence": "medium",
                "summary": "Missing empty state.",
                "evidence": "items.map(...)",
                "risk": "Users may see a blank screen.",
                "expected_improvement": "Add an empty state.",
                "verification": "Rerun quality-runner.",
            }
        ],
    }

    result = validate_skill_review_report(report, skills=skills, repo_root=tmp_path)
    assert result["accepted_count"] == 0
    assert result["rejected_count"] == 1


def test_skill_review_report_findings_merge_into_code_quality_scan(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_path = _install_skill(tmp_path, "ui-polish", _agent_review_skill_toml())
    _write(tmp_path / "apps/web/page.tsx", "export const Page = () => null;\n")
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path}],
    )
    report = {
        "schema": SKILL_REVIEW_REPORT_SCHEMA,
        "run_id": "run-001",
        "findings": [
            {
                "skill_id": "ui-polish",
                "review_id": "ui-polish-review",
                "rule_id": "ui-polish-review/missing-empty-state",
                "severity": "observation",
                "confidence": "medium",
                "file": "apps/web/page.tsx",
                "line": 1,
                "summary": "Collection UI renders results without an empty state.",
                "evidence": "export const Page = () => null;",
                "risk": "Users may see a blank or confusing screen.",
                "expected_improvement": "Add an empty state.",
                "verification": "Rerun quality-runner.",
            }
        ],
    }

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config=config,
        skill_review_report=report,
    )
    matches = [
        finding
        for finding in result["findings"]
        if finding["rule_id"] == "ui-polish-review/missing-empty-state"
    ]
    assert len(matches) == 1
    assert matches[0]["category"] == "skill:ui-polish"


def test_quality_skill_metadata_surfaces_in_audit_report(tmp_path: Path) -> None:
    from quality_runner.audit import build_audit_report, render_audit_markdown
    from quality_runner.code_quality import create_code_quality_scan

    skill_path = _install_skill(tmp_path, "ui-polish", _clickable_div_skill_toml())
    _write(tmp_path / "apps/web/page.tsx", "<div onClick={onOpen}>Open</div>\n")
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path}],
    )
    code_quality_scan = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config=config,
    )

    report = build_audit_report(
        scan={"run_id": "scan-001", "repo_root": str(tmp_path)},
        standards_packet={"profile": "default"},
        capability_map={"missing": [], "warnings": []},
        code_quality_scan=code_quality_scan,
    )

    finding = next(
        finding
        for finding in report["findings"]
        if finding.get("rule_message")
        == "Clickable divs should usually be semantic buttons or links."
    )
    assert finding["rule_category"] == "accessibility"
    assert "Clickable divs should usually be semantic buttons or links." in finding["summary"]
    assert "Rule category: accessibility" in render_audit_markdown(report)


def test_skill_review_report_rejects_inactive_skill(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_path = _install_skill(tmp_path, "ui-polish", _agent_review_skill_toml())
    config = _skills_enabled_config(
        active=[],
        local=[{"id": "ui-polish", "path": skill_path}],
    )
    report = {
        "schema": SKILL_REVIEW_REPORT_SCHEMA,
        "run_id": "run-001",
        "findings": [
            {
                "skill_id": "ui-polish",
                "review_id": "ui-polish-review",
                "rule_id": "ui-polish-review/missing-empty-state",
                "severity": "observation",
                "confidence": "medium",
                "file": "apps/web/page.tsx",
                "line": 1,
                "summary": "Missing empty state.",
                "evidence": "items.map(...)",
                "risk": "Users may see a blank screen.",
                "expected_improvement": "Add an empty state.",
                "verification": "Rerun quality-runner.",
            }
        ],
    }

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config=config,
        skill_review_report=report,
    )
    assert not any(str(finding["category"]).startswith("skill:") for finding in result["findings"])


def test_skill_ingest_dry_run_validates_candidate_without_writing(tmp_path: Path) -> None:
    from quality_runner.skill_ingest import ingest_skill_pack

    candidate = tmp_path / "candidate.toml"
    candidate.write_text(_clickable_div_skill_toml(), encoding="utf-8")

    result = ingest_skill_pack(
        candidate,
        skill_id="ui-polish",
        repo_root=tmp_path,
        write=False,
    )

    assert result["status"] == "validated"
    assert result["write"] is False
    assert not (tmp_path / ".quality-runner/skills/ui-polish.toml").exists()
    assert not (tmp_path / ".quality-runner.toml").exists()


def test_skill_ingest_write_registers_skill_and_updates_config(tmp_path: Path) -> None:
    from quality_runner.skill_ingest import ingest_skill_pack

    candidate = tmp_path / "candidate.toml"
    candidate.write_text(_clickable_div_skill_toml(), encoding="utf-8")

    result = ingest_skill_pack(
        candidate,
        skill_id="ui-polish",
        repo_root=tmp_path,
        activate=True,
        write=True,
    )

    assert result["status"] == "registered"
    assert (tmp_path / ".quality-runner/skills/ui-polish.toml").exists()
    config_text = (tmp_path / ".quality-runner.toml").read_text(encoding="utf-8")
    assert "ui-polish" in config_text
    assert result["active"] is True


def test_skill_ingest_rejects_path_traversal_skill_id(tmp_path: Path) -> None:
    from quality_runner.skill_ingest import ingest_skill_pack

    candidate = tmp_path / "candidate.toml"
    candidate.write_text(_clickable_div_skill_toml(), encoding="utf-8")

    result = ingest_skill_pack(
        candidate,
        skill_id="../bad",
        repo_root=tmp_path,
        write=False,
    )

    assert result["status"] == "rejected"


def test_skill_ingest_rejects_malformed_candidate(tmp_path: Path) -> None:
    from quality_runner.skill_ingest import ingest_skill_pack

    candidate = tmp_path / "candidate.toml"
    candidate.write_text("not valid toml [[", encoding="utf-8")

    result = ingest_skill_pack(
        candidate,
        skill_id="ui-polish",
        repo_root=tmp_path,
        write=False,
    )

    assert result["status"] == "rejected"


def test_skill_ingest_agent_prompt_exists_and_mentions_deterministic_vs_agent_review() -> None:
    prompt = Path("docs/skill-ingest-agent.md").read_text(encoding="utf-8")
    assert "deterministic" in prompt.lower()
    assert "agent_reviews" in prompt or "agent review" in prompt.lower()
