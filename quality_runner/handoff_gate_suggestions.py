from __future__ import annotations


def gate_severity(capability_id: str) -> str:
    if capability_id in {"formatter", "lint", "typecheck", "tests", "dead_code", "truth_file"}:
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
