from __future__ import annotations

import json
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


def _ui_specificity_skill_toml() -> str:
    return (Path(__file__).parents[1] / "docs/examples/ui-specificity.toml").read_text(
        encoding="utf-8"
    )


def _copy_specificity_skill_toml() -> str:
    return (Path(__file__).parents[1] / "docs/examples/copy-specificity.toml").read_text(
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


def _data_integrity_skill_toml() -> str:
    return (Path(__file__).parents[1] / "docs/examples/data-integrity.toml").read_text(
        encoding="utf-8"
    )


def _developer_experience_skill_toml() -> str:
    return (Path(__file__).parents[1] / "docs/examples/developer-experience.toml").read_text(
        encoding="utf-8"
    )


def _architecture_maintainability_skill_toml() -> str:
    return (
        Path(__file__).parents[1] / "docs/examples/architecture-maintainability.toml"
    ).read_text(encoding="utf-8")


def _performance_readiness_skill_toml() -> str:
    return (Path(__file__).parents[1] / "docs/examples/performance-readiness.toml").read_text(
        encoding="utf-8"
    )


def _motion_quality_skill_toml() -> str:
    return (Path(__file__).parents[1] / "docs/examples/motion-quality.toml").read_text(
        encoding="utf-8"
    )


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


def test_quality_skill_scans_frontend_source_extensions(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_content = _clickable_div_skill_toml().replace(
        'paths = ["**/*.tsx", "**/*.jsx"]',
        'paths = ["**/*.astro", "**/*.less", "**/*.mdx", "**/*.sass", "**/*.scss", '
        '"**/*.svelte", "**/*.vue"]',
    )
    skill_path = _install_skill(tmp_path, "ui-polish", skill_content)
    relative_paths = {
        "apps/web/page.astro",
        "apps/web/page.less",
        "apps/web/page.mdx",
        "apps/web/page.sass",
        "apps/web/page.scss",
        "apps/web/page.svelte",
        "apps/web/page.vue",
    }
    for relative_path in relative_paths:
        _write(tmp_path / relative_path, "<div onClick={onOpen}>Open</div>\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-frontend-extensions"},
        config=_skills_enabled_config(
            active=["ui-polish"],
            local=[{"id": "ui-polish", "path": skill_path}],
        ),
    )

    matched_paths = {
        str(finding["file"])
        for finding in result["findings"]
        if finding["rule_id"] == "ui-polish/ui-clickable-div"
    }
    assert matched_paths == relative_paths


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
    _write(
        tmp_path / "src/components/Nav.tsx",
        "export function Nav({ links }) {\n"
        "  return PAGE_LINKS.map((link) => <a key={link.path}>{link.label}</a>);\n"
        "}\n",
    )
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
    assert not any(
        finding["file"] == "src/components/Nav.tsx"
        and finding["rule_id"] == "ui-foundations/collection-empty-state"
        for finding in result["findings"]
    )
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


def test_ui_specificity_pack_keeps_visual_signals_reviewable(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import build_skill_review_packet

    skill_path = _install_skill(tmp_path, "ui-specificity", _ui_specificity_skill_toml())
    _write(
        tmp_path / "src/components/Hero.tsx",
        'export const Hero = () => <section className="bg-gradient-to-r '
        'from-indigo-500 to-purple-500 shadow-purple-500/50 rounded-full" />;\n',
    )
    _write(tmp_path / "src/styles.scss", ".glass { backdrop-filter: blur(20px); }\n")
    config = _skills_enabled_config(
        active=["ui-specificity"],
        local=[{"id": "ui-specificity", "path": skill_path}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "ui-specificity"}, config=config)
    rule_ids = {str(finding["rule_id"]) for finding in result["findings"]}
    assert {
        "ui-specificity/multi-hue-accent-gradient",
        "ui-specificity/accent-colored-glow",
        "ui-specificity/translucent-blur-surface",
        "ui-specificity/pill-shaped-surface",
    } <= rule_ids
    assert all(
        finding["severity"] == "observation"
        for finding in result["findings"]
        if str(finding["rule_id"]).startswith("ui-specificity/")
    )

    skills, warnings = load_active_skills(tmp_path, config)
    assert warnings == []
    assert skills[0]["sources"][0]["id"] == "kill-ai-slop-clean-room"
    packet = build_skill_review_packet(
        run_id="ui-specificity",
        repo_root=tmp_path,
        scanned_files=[
            {"path": "src/components/Hero.tsx", "lines": ["<section />"]},
            {"path": "src/styles.scss", "lines": [".glass { backdrop-filter: blur(20px); }"]},
        ],
        skills=skills,
    )
    assert packet is not None
    assert {review["review_id"] for review in packet["reviews"]} == {"visual-intent-and-system-fit"}


def test_copy_specificity_pack_is_scoped_to_product_content(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    skill_path = _install_skill(tmp_path, "copy-specificity", _copy_specificity_skill_toml())
    _write(
        tmp_path / "apps/web/content/landing.mdx",
        "Not just a dashboard — it's the workflow your support team can measure.\n"
        "Build a seamless handoff from the same source.\n",
    )
    _write(tmp_path / "docs/example.md", "Not just a test fixture — it's an example.\n")
    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "copy-specificity"},
        config=_skills_enabled_config(
            active=["copy-specificity"],
            local=[{"id": "copy-specificity", "path": skill_path}],
        ),
    )

    matches = [
        finding
        for finding in result["findings"]
        if str(finding["rule_id"]).startswith("copy-specificity/")
    ]
    assert {str(finding["file"]) for finding in matches} == {"apps/web/content/landing.mdx"}
    assert {str(finding["rule_id"]) for finding in matches} == {
        "copy-specificity/contrastive-slogan",
        "copy-specificity/generic-benefit-language",
    }


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


def test_data_integrity_pack_reports_migration_signals_and_review_scopes(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import build_skill_review_packet

    skill_path = _install_skill(tmp_path, "data-integrity", _data_integrity_skill_toml())
    migration = "DROP TABLE users;\nDELETE FROM sessions;\n"
    _write(tmp_path / "db/migrations/001_cleanup.sql", migration)
    config = _skills_enabled_config(
        active=["data-integrity"],
        local=[{"id": "data-integrity", "path": skill_path}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "data-integrity"}, config=config)
    rule_ids = {str(finding["rule_id"]) for finding in result["findings"]}
    assert "data-integrity/destructive-schema-operation" in rule_ids
    assert "data-integrity/unconditional-delete-operation" in rule_ids
    assert result["quality_skills"][0]["id"] == "data-integrity"

    reviewed = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "data-integrity-reviewed"},
        config=config,
        skill_review_report={
            "schema": SKILL_REVIEW_REPORT_SCHEMA,
            "run_id": "data-integrity-reviewed",
            "findings": [
                {
                    "skill_id": "data-integrity",
                    "review_id": "migration-and-backfill",
                    "rule_id": "migration-and-backfill/missing-recovery-plan",
                    "severity": "observation",
                    "confidence": "low",
                    "file": "db/migrations/001_cleanup.sql",
                    "line": 1,
                    "summary": "The destructive migration has no visible recovery or forward-fix evidence.",
                    "evidence": "DROP TABLE users;",
                    "risk": "A partial or incorrect migration could remove data without a recoverable path.",
                    "expected_improvement": "Add or cite backup, restore, rollback, or forward-fix verification for the migration.",
                    "verification": "Rerun quality-runner and the migration verification command after adding the recovery evidence.",
                }
            ],
        },
    )
    assert any(
        finding["rule_id"] == "migration-and-backfill/missing-recovery-plan"
        for finding in reviewed["findings"]
    )

    skills, warnings = load_active_skills(tmp_path, config)
    assert warnings == []
    packet = build_skill_review_packet(
        run_id="data-integrity",
        repo_root=tmp_path,
        scanned_files=[{"path": "db/migrations/001_cleanup.sql", "lines": migration.splitlines()}],
        skills=skills,
    )
    assert packet is not None
    assert len(packet["reviews"]) == 5
    assert {review["review_id"] for review in packet["reviews"]} == {
        "schema-and-invariants",
        "migration-and-backfill",
        "pipeline-and-reconciliation",
        "data-loss-and-duplication",
        "verification-and-fixtures",
    }
    assert len(packet["included_files"]) == 1


def test_developer_experience_pack_reports_docs_signals_and_review_scopes(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import build_skill_review_packet

    skill_path = _install_skill(
        tmp_path, "developer-experience", _developer_experience_skill_toml()
    )
    readme = "# Setup\n\nTODO: document the test command at /Users/jakyeamos/projects/app.\n"
    _write(tmp_path / "README.md", readme)
    config = _skills_enabled_config(
        active=["developer-experience"],
        local=[{"id": "developer-experience", "path": skill_path}],
    )

    result = create_code_quality_scan(
        tmp_path, scan={"run_id": "developer-experience"}, config=config
    )
    rule_ids = {str(finding["rule_id"]) for finding in result["findings"]}
    assert "developer-experience/placeholder-documentation" in rule_ids
    assert "developer-experience/machine-specific-setup-path" in rule_ids
    assert result["quality_skills"][0]["id"] == "developer-experience"

    reviewed = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "developer-experience-reviewed"},
        config=config,
        skill_review_report={
            "schema": SKILL_REVIEW_REPORT_SCHEMA,
            "run_id": "developer-experience-reviewed",
            "findings": [
                {
                    "skill_id": "developer-experience",
                    "review_id": "onboarding-and-setup",
                    "rule_id": "onboarding-and-setup/missing-first-run-proof",
                    "severity": "observation",
                    "confidence": "low",
                    "file": "README.md",
                    "line": 1,
                    "summary": "The onboarding guide does not show a verified first-run path.",
                    "evidence": "# Setup",
                    "risk": "Contributors may not know which command proves that setup succeeded.",
                    "expected_improvement": "Document the install, first-run, and verification commands with expected results.",
                    "verification": "Rerun quality-runner and follow the documented setup path from a clean environment.",
                }
            ],
        },
    )
    assert any(
        finding["rule_id"] == "onboarding-and-setup/missing-first-run-proof"
        for finding in reviewed["findings"]
    )

    skills, warnings = load_active_skills(tmp_path, config)
    assert warnings == []
    packet = build_skill_review_packet(
        run_id="developer-experience",
        repo_root=tmp_path,
        scanned_files=[{"path": "README.md", "lines": readme.splitlines()}],
        skills=skills,
    )
    assert packet is not None
    assert len(packet["reviews"]) == 5
    assert {review["review_id"] for review in packet["reviews"]} == {
        "onboarding-and-setup",
        "command-discoverability",
        "contribution-and-ci",
        "repository-wayfinding",
        "maintainer-handoff",
    }
    assert len(packet["included_files"]) == 1


def test_architecture_maintainability_pack_reports_seams_and_review_scopes(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import build_skill_review_packet

    skill_path = _install_skill(
        tmp_path,
        "architecture-maintainability",
        _architecture_maintainability_skill_toml(),
    )
    source = "def legacy_adapter(value):\n    return value\n"
    _write(tmp_path / "src/compat.py", source)
    _write(
        tmp_path / "src/ordinary.py",
        "def calculate_compatibility_score(value):\n    return value\n",
    )
    config = _skills_enabled_config(
        active=["architecture-maintainability"],
        local=[{"id": "architecture-maintainability", "path": skill_path}],
    )

    result = create_code_quality_scan(
        tmp_path, scan={"run_id": "architecture-maintainability"}, config=config
    )
    rule_ids = {str(finding["rule_id"]) for finding in result["findings"]}
    assert "architecture-maintainability/compatibility-seam-without-removal-boundary" in rule_ids
    assert not any(
        finding["file"] == "src/ordinary.py"
        and finding["rule_id"]
        == "architecture-maintainability/compatibility-seam-without-removal-boundary"
        for finding in result["findings"]
    )
    assert result["quality_skills"][0]["id"] == "architecture-maintainability"

    reviewed = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "architecture-maintainability-reviewed"},
        config=config,
        skill_review_report={
            "schema": SKILL_REVIEW_REPORT_SCHEMA,
            "run_id": "architecture-maintainability-reviewed",
            "findings": [
                {
                    "skill_id": "architecture-maintainability",
                    "review_id": "ownership-and-boundaries",
                    "rule_id": "ownership-and-boundaries/duplicate-owner",
                    "severity": "observation",
                    "confidence": "low",
                    "file": "src/compat.py",
                    "line": 1,
                    "summary": "The compatibility helper may duplicate an existing contract owner.",
                    "evidence": "def legacy_adapter(value):",
                    "risk": "A second owner can let the compatibility behavior drift from the canonical contract.",
                    "expected_improvement": "Identify the canonical owner and either consume it directly or document the external boundary and removal condition.",
                    "verification": "Rerun quality-runner and the consumer tests after confirming the ownership boundary.",
                }
            ],
        },
    )
    assert any(
        finding["rule_id"] == "ownership-and-boundaries/duplicate-owner"
        for finding in reviewed["findings"]
    )

    skills, warnings = load_active_skills(tmp_path, config)
    assert warnings == []
    packet = build_skill_review_packet(
        run_id="architecture-maintainability",
        repo_root=tmp_path,
        scanned_files=[{"path": "src/compat.py", "lines": source.splitlines()}],
        skills=skills,
    )
    assert packet is not None
    assert len(packet["reviews"]) == 5
    assert {review["review_id"] for review in packet["reviews"]} == {
        "ownership-and-boundaries",
        "duplication-and-single-source",
        "decision-and-tradeoffs",
        "complexity-and-maintainability",
        "compatibility-and-removal",
    }
    assert len(packet["included_files"]) == 1


def test_performance_readiness_pack_reports_static_signals_and_review_scopes(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import build_skill_review_packet

    skill_path = _install_skill(
        tmp_path, "performance-readiness", _performance_readiness_skill_toml()
    )
    source = (
        "def load_users(cursor):\n"
        "    time.sleep(1)\n"
        "    return cursor.execute('SELECT * FROM users')\n"
    )
    _write(tmp_path / "src/query.py", source)
    config = _skills_enabled_config(
        active=["performance-readiness"],
        local=[{"id": "performance-readiness", "path": skill_path}],
    )

    result = create_code_quality_scan(
        tmp_path, scan={"run_id": "performance-readiness"}, config=config
    )
    rule_ids = {str(finding["rule_id"]) for finding in result["findings"]}
    assert "performance-readiness/select-star" in rule_ids
    assert "performance-readiness/blocking-call-in-source" in rule_ids
    assert result["quality_skills"][0]["id"] == "performance-readiness"

    reviewed = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "performance-readiness-reviewed"},
        config=config,
        skill_review_report={
            "schema": SKILL_REVIEW_REPORT_SCHEMA,
            "run_id": "performance-readiness-reviewed",
            "findings": [
                {
                    "skill_id": "performance-readiness",
                    "review_id": "measurement-and-profiling",
                    "rule_id": "measurement-and-profiling/missing-baseline",
                    "severity": "observation",
                    "confidence": "low",
                    "file": "src/query.py",
                    "line": 1,
                    "summary": "The database access path has no visible baseline or profiling evidence.",
                    "evidence": "def load_users(cursor):",
                    "risk": "A query or blocking-call change could regress latency without a measured comparison.",
                    "expected_improvement": "Add a representative benchmark or profiling check for the user-loading path.",
                    "verification": "Rerun quality-runner and the performance verification command after adding the baseline.",
                }
            ],
        },
    )
    assert any(
        finding["rule_id"] == "measurement-and-profiling/missing-baseline"
        for finding in reviewed["findings"]
    )

    skills, warnings = load_active_skills(tmp_path, config)
    assert warnings == []
    packet = build_skill_review_packet(
        run_id="performance-readiness",
        repo_root=tmp_path,
        scanned_files=[{"path": "src/query.py", "lines": source.splitlines()}],
        skills=skills,
    )
    assert packet is not None
    assert len(packet["reviews"]) == 5
    assert {review["review_id"] for review in packet["reviews"]} == {
        "measurement-and-profiling",
        "hot-path-and-scaling",
        "io-and-concurrency",
        "bundle-and-runtime",
        "verification-and-load",
    }
    assert len(packet["included_files"]) == 1


def test_motion_quality_pack_reports_motion_signals_and_review_scopes(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import build_skill_review_packet

    skill_path = _install_skill(tmp_path, "motion-quality", _motion_quality_skill_toml())
    styles = (
        ".panel { transition: all 500ms ease-in; }\n"
        ".drawer { transition: width 300ms; transform: scale(0); }\n"
        "@keyframes slide { from { opacity: 0; } to { opacity: 1; } }\n"
    )
    _write(tmp_path / "src/motion.css", styles)
    config = _skills_enabled_config(
        active=["motion-quality"],
        local=[{"id": "motion-quality", "path": skill_path}],
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "motion-quality"}, config=config)
    rule_ids = {str(finding["rule_id"]) for finding in result["findings"]}
    assert "motion-quality/unbounded-transition" in rule_ids
    assert "motion-quality/layout-property-animation" in rule_ids
    assert "motion-quality/scale-zero-entry" in rule_ids
    assert "motion-quality/ease-in-ui-motion" in rule_ids
    assert "motion-quality/motion-without-reduced-motion" in rule_ids
    assert result["quality_skills"][0]["id"] == "motion-quality"

    reviewed = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "motion-quality-reviewed"},
        config=config,
        skill_review_report={
            "schema": SKILL_REVIEW_REPORT_SCHEMA,
            "run_id": "motion-quality-reviewed",
            "findings": [
                {
                    "skill_id": "motion-quality",
                    "review_id": "purpose-and-frequency",
                    "rule_id": "purpose-and-frequency/unjustified-motion",
                    "severity": "observation",
                    "confidence": "low",
                    "file": "src/motion.css",
                    "line": 1,
                    "summary": "The panel animation has no visible purpose or frequency justification.",
                    "evidence": ".panel { transition: all 500ms ease-in; }",
                    "risk": "Frequently seen motion may make the interface feel slower without improving comprehension or feedback.",
                    "expected_improvement": "Delete or reduce the animation unless the interaction has a clear spatial, state, or feedback purpose.",
                    "verification": "Review the interaction at normal and reduced motion settings, then rerun quality-runner.",
                }
            ],
        },
    )
    assert any(
        finding["rule_id"] == "purpose-and-frequency/unjustified-motion"
        for finding in reviewed["findings"]
    )

    skills, warnings = load_active_skills(tmp_path, config)
    assert warnings == []
    packet = build_skill_review_packet(
        run_id="motion-quality",
        repo_root=tmp_path,
        scanned_files=[{"path": "src/motion.css", "lines": styles.splitlines()}],
        skills=skills,
    )
    assert packet is not None
    assert len(packet["reviews"]) == 5
    assert {review["review_id"] for review in packet["reviews"]} == {
        "purpose-and-frequency",
        "easing-duration-and-origin",
        "interruptibility-and-performance",
        "accessibility-and-pointer-gating",
        "cohesion-and-simplification",
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


def test_quality_skill_ingest_rejects_invalid_regex_with_precise_error(tmp_path: Path) -> None:
    from quality_runner.skill_ingest import ingest_skill_pack

    candidate = tmp_path / "candidate.toml"
    candidate.write_text(
        _clickable_div_skill_toml().replace(
            'disallowed_patterns = ["<div[^>]+onClick="]',
            'disallowed_patterns = ["["]',
        ),
        encoding="utf-8",
    )

    result = ingest_skill_pack(
        candidate,
        skill_id="ui-polish",
        repo_root=tmp_path,
        write=False,
    )

    assert result["status"] == "rejected"
    assert any(
        "deterministic_rules[0] ui-clickable-div disallowed_patterns[0]"
        " invalid regular expression" in error
        for error in result["errors"]
    )


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
        "execution_mode": "automatic",
        "required_review_count": 1,
    }


def test_active_skill_review_blocks_handoff_until_agent_report_is_merged(tmp_path: Path) -> None:
    from quality_runner.run_summary import build_run_summary
    from quality_runner.workflow import run_payload
    from test_support.quality_runner_fixtures import write_js_fixture

    write_js_fixture(tmp_path)
    skill_path = _install_skill(tmp_path, "ui-polish", _agent_review_skill_toml())
    _write(tmp_path / "apps/web/page.tsx", "export const Page = () => null;\n")
    _write(
        tmp_path / ".quality-runner.toml",
        "\n".join(
            [
                "[quality_runner.skills]",
                "enabled = true",
                "",
                "[[quality_runner.skills.local]]",
                'id = "ui-polish"',
                f'path = "{skill_path}"',
                "",
            ]
        ),
    )

    payload = run_payload(
        repo_root=tmp_path,
        run_id="skill-review-required",
        agent_review_mode="required",
    )
    handoff_path = Path(payload["artifact_paths"]["agent_handoff_json"])
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))

    assert payload["status"] == "review-required"
    assert handoff["status"] == "review-required"
    assert handoff["lifecycle_status"] == "blocked"
    assert handoff["skill_review"]["status"] == "review-required"
    assert handoff["skill_review"]["unresolved_review_ids"] == ["ui-polish/ui-polish-review"]
    assert Path(handoff["skill_review"]["packet_json"]).exists()
    markdown = handoff_path.with_name("agent-handoff.md").read_text(encoding="utf-8")
    assert "Action required: read the review packet" in markdown

    summary = build_run_summary(repo_root=tmp_path, run_id="skill-review-required")
    assert summary["status"] == "blocked"
    assert summary["recommended_classification"] == "review-required-blocker"
    assert "review-required" in summary["blocker_classes"]


def test_parallel_skill_review_is_pending_without_blocking_qr(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload
    from test_support.quality_runner_fixtures import write_js_fixture

    write_js_fixture(tmp_path)
    skill_path = _install_skill(tmp_path, "ui-polish", _agent_review_skill_toml())
    _write(tmp_path / "apps/web/page.tsx", "export const Page = () => null;\n")
    _write(
        tmp_path / ".quality-runner.toml",
        "\n".join(
            [
                "[quality_runner.skills]",
                "enabled = true",
                'agent_review_mode = "parallel"',
                "",
                "[[quality_runner.skills.local]]",
                'id = "ui-polish"',
                f'path = "{skill_path}"',
                "",
            ]
        ),
    )

    payload = run_payload(repo_root=tmp_path, run_id="skill-review-parallel")

    handoff = json.loads(
        Path(payload["artifact_paths"]["agent_handoff_json"]).read_text(encoding="utf-8")
    )
    skill_review = handoff["skill_review"]
    assert payload["status"] in {"clean", "planned"}
    assert handoff["status"] != "review-required"
    assert skill_review["mode"] == "parallel"
    assert skill_review["status"] == "review-pending"
    assert skill_review["unresolved_review_ids"] == ["ui-polish/ui-polish-review"]
    assert Path(skill_review["packet_json"]).exists()


def test_agent_reviews_can_be_disabled_without_emitting_a_packet(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload
    from test_support.quality_runner_fixtures import write_js_fixture

    write_js_fixture(tmp_path)
    skill_path = _install_skill(tmp_path, "ui-polish", _agent_review_skill_toml())
    _write(tmp_path / "apps/web/page.tsx", "export const Page = () => null;\n")
    _write(
        tmp_path / ".quality-runner.toml",
        "\n".join(
            [
                "[quality_runner.skills]",
                "enabled = true",
                'agent_review_mode = "off"',
                "",
                "[[quality_runner.skills.local]]",
                'id = "ui-polish"',
                f'path = "{skill_path}"',
                "",
            ]
        ),
    )

    payload = run_payload(repo_root=tmp_path, run_id="skill-review-off")

    handoff = json.loads(
        Path(payload["artifact_paths"]["agent_handoff_json"]).read_text(encoding="utf-8")
    )
    skill_review = handoff["skill_review"]
    assert payload["status"] in {"clean", "planned"}
    assert skill_review["mode"] == "off"
    assert skill_review["status"] == "not-run"
    assert "packet_json" not in skill_review
    assert not (
        tmp_path / ".quality-runner/runs/skill-review-off/skill-review-packet.json"
    ).exists()


def test_skill_review_report_merges_across_runs(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload
    from test_support.quality_runner_fixtures import write_js_fixture

    write_js_fixture(tmp_path)
    skill_path = _install_skill(tmp_path, "ui-polish", _agent_review_skill_toml())
    _write(tmp_path / "apps/web/page.tsx", "export const Page = () => null;\n")
    _write(
        tmp_path / ".quality-runner.toml",
        "\n".join(
            [
                "[quality_runner.skills]",
                "enabled = true",
                "",
                "[[quality_runner.skills.local]]",
                'id = "ui-polish"',
                f'path = "{skill_path}"',
                "",
            ]
        ),
    )

    first = run_payload(repo_root=tmp_path, run_id="skill-review-packet")
    packet = json.loads(
        Path(first["artifact_paths"]["skill_review_packet_json"]).read_text(encoding="utf-8")
    )
    report = {
        "schema": SKILL_REVIEW_REPORT_SCHEMA,
        "run_id": packet["run_id"],
        "findings": [],
        "reviewed_review_ids": ["ui-polish/ui-polish-review"],
    }

    second = run_payload(
        repo_root=tmp_path,
        run_id="skill-review-merged",
        skill_review_report=report,
    )
    handoff = json.loads(
        Path(second["artifact_paths"]["agent_handoff_json"]).read_text(encoding="utf-8")
    )

    assert second["status"] in {"clean", "planned"}
    assert handoff["status"] != "review-required"
    assert handoff["skill_review"]["status"] == "reviewed"
    assert handoff["skill_review"]["report_source_run_id"] == "skill-review-packet"
    assert Path(handoff["skill_review"]["report_json"]).exists()


def test_auto_skill_review_requires_every_active_review_to_be_covered(tmp_path: Path) -> None:
    from quality_runner.skill_config import load_active_skills
    from quality_runner.skill_review import validate_skill_review_report

    skill_path = _install_skill(tmp_path, "ui-polish", _agent_review_skill_toml())
    config = _skills_enabled_config(
        active=["ui-polish"],
        local=[{"id": "ui-polish", "path": skill_path}],
    )
    skills, _warnings = load_active_skills(tmp_path, config)

    result = validate_skill_review_report(
        {
            "schema": SKILL_REVIEW_REPORT_SCHEMA,
            "run_id": "run-001",
            "findings": [],
        },
        skills=skills,
        repo_root=tmp_path,
        require_review_coverage=True,
    )

    assert result["status"] == "rejected"
    assert "reviewed_review_ids" in result["errors"][0]


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
    assert finding["category"] == "skill:ui-polish"
    assert finding["actionability"] == "needs-maintainer-policy"
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
