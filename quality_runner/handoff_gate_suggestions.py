from __future__ import annotations


def gate_severity(capability_id: str) -> str:
    if capability_id in {
        "formatter",
        "lint",
        "typecheck",
        "tests",
        "dead_code",
        "truth_file",
        "evidence_provenance",
        "release_manifest_coherence",
        "package_consumer_smoke",
        "migration_safety",
        "release_acceptance_evidence",
        "aggregate_coverage",
        "read_only_integrity",
        "publication_visibility_review",
    }:
        return "blocker"
    return "warning"


def suggested_gate_command(capability_id: str, language: object) -> str:
    python_commands = {
        "formatter": "ruff format --check .",
        "lint": "ruff check .",
        "typecheck": "basedpyright",
        "tests": "pytest -q",
        "build": "uv build",
        "dead_code": "vulture . --min-confidence 70",
        "runtime_smoke": "python -m <package_or_console_script>",
        "pre_pr": "quality-runner run . --json",
        "pre_cr": "pre-cr run --workspace . --json",
        "truth_file": "maintain .tracker/PROJECT_TRUTH.md",
        "package_consumer_smoke": "add package-smoke or consumer-smoke and install the built artifact in isolation",
        "migration_safety": "provide forward, rollback, failure-injection, and reconciliation evidence",
        "release_acceptance_evidence": "provide the release-evidence.json owner acceptance record",
        "evidence_provenance": "provide current-HEAD-matched CI provenance",
        "release_manifest_coherence": "align package metadata, artifact version, source HEAD, and digest",
        "aggregate_coverage": "expand aggregate scripts and prove all required leaf gates are covered",
        "read_only_integrity": "rerun mutating or unknown-risk gates in a disposable worktree and inspect mutation diagnostics",
        "publication_visibility_review": "complete authorization, sanitization, publication-versioning, and media-access review evidence",
    }
    javascript_commands = {
        "formatter": "pnpm format",
        "lint": "pnpm lint",
        "typecheck": "pnpm typecheck",
        "tests": "pnpm test",
        "build": "pnpm build",
        "dead_code": "pnpm audit:dead-code",
        "runtime_smoke": "pnpm smoke",
        "pre_pr": "pnpm pre-pr",
        "pre_cr": "pnpm pre-cr",
        "truth_file": "maintain .tracker/PROJECT_TRUTH.md",
        "security_secrets_scan": "gitleaks detect --source .",
        "security_dependency_audit": "pnpm audit --audit-level high",
        "security_static_analysis": "semgrep --config auto",
    }
    commands = python_commands if language == "python" else javascript_commands
    return commands.get(capability_id, f"add a {capability_id} gate")
