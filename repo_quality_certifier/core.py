from __future__ import annotations

import json
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_SCAN_SCHEMA = "aios-repo-gate-scan-v0.1"
GATE_MATRIX_SCHEMA = "aios-repo-gate-matrix-v0.1"
TMCP_EXPERT_ENRICHMENT_SCHEMA = "aios-repo-gate-tmcp-expert-enrichment-v0.1"
RUBRIC_PACK_SCHEMA = "aios-repo-gate-rubric-pack-v0.1"
RUBRIC_AUDIT_SCHEMA = "aios-repo-gate-rubric-audit-v0.1"
RUBRIC_IMPLEMENTATION_SCHEMA = "aios-repo-gate-rubric-implementation-v0.1"
RUBRIC_DETAIL_MANIFEST_SCHEMA = "aios-repo-gate-rubric-detail-manifest-v0.1"
ADOPTION_DOC_QUALITY_SCHEMA = "aios-repo-gate-adoption-doc-quality-v0.1"
GATE_ROLLOUT_PLAN_SCHEMA = "aios-repo-gate-rollout-plan-v0.2"
AIOS_BACKFILL_DIR_NAME = "AIOS-backfill"
PHASE_PLANNING_BLOCKING_WARNING_CODES = {
    "audit_empty_section": "Generated audit docs still contain empty placeholder sections.",
    "audit_no_known_evidence": "Audit docs are missing repo-specific evidence.",
    "implementation_empty_section": "Generated implementation docs still contain empty placeholder sections.",
    "implementation_generic_root_cause": "Implementation docs still contain generic root-cause text.",
}
QUALITY_PIPELINE_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "quality-pipeline.json"
)
TmcpCompiler = Callable[..., dict[str, Any]]

CORE_GATE_IDS = (
    "install",
    "formatter",
    "lint",
    "typecheck",
    "tests",
    "build",
    "package",
    "validation",
    "dead_code",
    "structural_scan",
    "complexity_budget",
    "secret_scan",
    "dependency_security",
    "mobile_release",
    "e2e_smoke",
    "runtime_smoke",
    "pre_pr_readiness",
    "release_rollback_readiness",
    "thermo_nuclear_simplification",
    "pre_cr",
    "anti_slop",
    "data_state_integrity",
    "observability_debuggability",
    "repo_truth",
    "local_quality_contract",
    "ci",
    "local_hook",
)

STRICT_CLEARANCE_GATE_IDS = frozenset({"lint", "tests"})

GATE_LABELS = {
    "install": "Frozen Install",
    "formatter": "Formatter",
    "lint": "Lint",
    "typecheck": "Typecheck",
    "tests": "Tests",
    "build": "Build",
    "package": "Package / Consumer Smoke",
    "validation": "Class-Specific Validation",
    "dead_code": "Dead-Code Scan",
    "structural_scan": "Structural / Anti-Slop Scan",
    "complexity_budget": "Complexity / Big-O Budget",
    "secret_scan": "Secret Scan",
    "dependency_security": "Dependency Security",
    "mobile_release": "Mobile Release",
    "e2e_smoke": "E2E Smoke",
    "runtime_smoke": "Runtime Smoke",
    "pre_pr_readiness": "Pre-PR Readiness",
    "release_rollback_readiness": "Release / Rollback Readiness",
    "thermo_nuclear_simplification": "Thermo-Nuclear Simplification",
    "pre_cr": "Pre-CR Changed-Line Readiness",
    "anti_slop": "Anti-Slop Heuristics",
    "data_state_integrity": "Data / State Integrity",
    "observability_debuggability": "Observability / Debuggability",
    "repo_truth": "Project Truth",
    "local_quality_contract": "AIOS Local Quality Contract",
    "ci": "Remote CI",
    "local_hook": "Local Hook Enforcement",
}

QUALITY_PROFILE_GATE_ALIASES = {
    "tests": ("test", "tests"),
    "formatter": ("formatter", "format"),
    "validation": ("validation", "validate", "env_validation"),
    "dead_code": ("dead_code", "dead-code"),
    "structural_scan": ("structural_scan", "architecture"),
    "complexity_budget": ("complexity_budget", "performance_budget", "performance"),
    "runtime_smoke": ("runtime_smoke", "runtime-smoke", "smoke"),
    "pre_pr_readiness": ("pre_pr_readiness", "pre_pr"),
    "release_rollback_readiness": (
        "release_rollback_readiness",
        "release-rollback-readiness",
        "release_readiness",
        "release-readiness",
    ),
    "thermo_nuclear_simplification": (
        "thermo_nuclear_simplification",
        "thermo-nuclear-simplification",
    ),
    "data_state_integrity": ("data_state_integrity", "data-state-integrity"),
    "observability_debuggability": (
        "observability_debuggability",
        "observability-debuggability",
    ),
}

GATE_SETUP_GUIDANCE = {
    "formatter": {
        "actions": [
            "Add or identify a repo-local formatter check command.",
            "Prefer check-only formatting for adoption certification before enabling write-mode formatting.",
        ],
        "commands": [
            "pnpm exec prettier --check .",
            "uv run ruff format --check .",
        ],
        "files": ["package.json:scripts.format", "pyproject.toml:tool.ruff"],
    },
    "validation": {
        "actions": [
            "Add a class-specific validation command for environment, data, content, or domain invariants.",
            "Wire the command into the AIOS quality profile when it is required for the repo class.",
        ],
        "commands": [
            "pnpm env:check",
            "python scripts/validate.py",
        ],
        "files": [
            "package.json:scripts.validate",
            "scripts/validate.py",
            ".aios-quality-gate.json",
        ],
    },
    "dead_code": {
        "actions": [
            "Add a dead-code inventory command appropriate to the language/runtime.",
            "Record dynamic-entry exceptions before using the result as removal proof.",
        ],
        "commands": [
            "pnpm exec knip",
            "uv run vulture . --min-confidence 70",
        ],
        "files": ["package.json:scripts.dead-code", "knip.json", "pyproject.toml:tool.vulture"],
    },
    "structural_scan": {
        "actions": [
            "Use the configured architecture gate as the structural scan when available.",
            "Otherwise add a repo-local architecture or structural anti-slop command.",
        ],
        "commands": [
            "node scripts/aios-architecture-check.mjs",
            "pnpm lint:architecture",
        ],
        "files": ["scripts/aios-architecture-check.mjs", "package.json:scripts.lint:architecture"],
    },
    "complexity_budget": {
        "actions": [
            "Add a complexity/performance-budget audit for hotspots before claiming broad simplification compliance.",
            "Start in audit mode if no reliable threshold exists yet.",
        ],
        "commands": [
            "pnpm complexity:check",
            "pnpm bench",
        ],
        "files": ["package.json:scripts.complexity:check", "docs/quality/complexity-budget.md"],
    },
    "pre_pr_readiness": {
        "actions": [
            "Add a pre-PR readiness command that runs the local quality ladder expected before review.",
            "Keep it separate from final release certification if it is intentionally lighter.",
        ],
        "commands": [
            "pnpm pre-pr",
            "pnpm pre-pr-readiness",
        ],
        "files": ["package.json:scripts.pre-pr", ".aios-quality-gate.json"],
    },
    "runtime_smoke": {
        "actions": [
            "Add a class-appropriate runtime smoke command that exercises the built or launched artifact.",
            "Use web browser/device/CLI/package/content smoke proof instead of treating build success as runtime proof.",
        ],
        "commands": [
            "pnpm smoke",
            "pnpm test:runtime-smoke",
            "python scripts/smoke.py",
        ],
        "files": ["package.json:scripts.smoke", "scripts/smoke.py", ".aios-quality-gate.json"],
    },
    "release_rollback_readiness": {
        "actions": [
            "Add release-readiness proof for deploy/package/version/migration readiness and rollback notes.",
            "For non-deployed repos, document the package or local release equivalent instead of skipping the gate silently.",
        ],
        "commands": [
            "pnpm release:check",
            "pnpm deploy:preview:watch",
            "python scripts/release_check.py",
        ],
        "files": [
            "package.json:scripts.release:check",
            "docs/release.md",
            "docs/rollback.md",
        ],
    },
    "thermo_nuclear_simplification": {
        "actions": [
            "Add a thermo-nuclear simplification audit for large or overgrown repos.",
            "Use the result to create simplification phases rather than inline broad rewrites.",
        ],
        "commands": [
            "pnpm thermo-nuclear-simplification",
            "python scripts/thermo_nuclear_simplification.py",
        ],
        "files": [
            "package.json:scripts.thermo-nuclear-simplification",
            "docs/quality/simplification-audit.md",
        ],
    },
    "data_state_integrity": {
        "actions": [
            "Add proof for migrations, seeds, queues, sync jobs, scraping, idempotency, or content/data validators where applicable.",
            "If the repo has no persistent state or data workflows, record a no-state accepted exception with classification evidence.",
        ],
        "commands": [
            "pnpm db:verify",
            "pnpm data:validate",
            "python scripts/validate_data.py",
        ],
        "files": [
            "migrations/",
            "supabase/migrations/",
            "prisma/schema.prisma",
            "scripts/validate_data.py",
        ],
    },
    "observability_debuggability": {
        "actions": [
            "Add proof that real failures are diagnosable through logs, health checks, error boundaries, traces, or structured diagnostics.",
            "Keep the proof lightweight, but make it enough for another agent to debug a failed runtime path.",
        ],
        "commands": [
            "pnpm healthcheck",
            "pnpm observability:check",
            "python scripts/healthcheck.py",
        ],
        "files": [
            "scripts/healthcheck.py",
            "docs/observability.md",
            "docs/debugging.md",
        ],
    },
    "local_quality_contract": {
        "actions": [
            "Add a repo-local `.aios-quality-gate.json` contract that names the AIOS project id and required adoption gates.",
            "Keep the contract aligned with the central AIOS quality profile instead of using it to weaken requirements.",
        ],
        "commands": [
            "test -f .aios-quality-gate.json",
            "python3 /Users/jakyeamos/AIOS/scripts/linked-repo-quality-runner.py --project <project>",
        ],
        "files": [".aios-quality-gate.json", "config/quality-gates.json"],
    },
}

BROAD_RUBRIC_IDS = (
    "build_package_integrity",
    "runtime_smoke_integrity",
    "complexity_simplification",
    "anti_slop_product_quality",
    "architecture_boundaries",
    "test_quality_value",
    "ui_visual_runtime_verification",
    "dead_code",
    "security_secret_handling",
    "dependency_risk",
    "truth_docs_accuracy",
    "ci_local_proof_integrity",
    "release_rollback_readiness",
    "data_state_integrity",
    "observability_debuggability",
)

BROAD_RUBRIC_DEFINITIONS = {
    "build_package_integrity": {
        "title": "Build And Package Integrity",
        "standard": "The repo can produce its production build, package, or consumer artifact through the documented command path.",
        "gate_caveat": "A passing typecheck or focused build does not prove the release artifact can be produced or consumed.",
        "required_evidence": [
            "full production build or package command result",
            "consumer smoke or artifact inspection where applicable",
            "package-manager and lockfile authority confirmed",
            "build exceptions documented with owner and expiry",
        ],
    },
    "runtime_smoke_integrity": {
        "title": "Runtime Smoke Integrity",
        "standard": "The built or launched artifact is exercised through the runtime path appropriate to the repo class.",
        "gate_caveat": "A passing build does not prove runtime behavior, route accessibility, CLI execution, simulator launch, or data/content validation.",
        "required_evidence": [
            "class-appropriate runtime smoke command",
            "local launch, CLI invocation, package import, simulator/device run, or content/data validator result",
            "representative success and failure path checked where applicable",
            "runtime blocker or no-runtime exception documented",
        ],
    },
    "complexity_simplification": {
        "title": "Complexity And Simplification",
        "standard": "The repo keeps core workflows understandable, deletes accidental complexity, proves performance-sensitive paths, and remains maintainable for the next likely change.",
        "gate_caveat": "Thermo/simplifier skills are expert audit engines for obvious structural complexity, but they do not alone prove runtime complexity, product complexity, architectural ownership, over-abstraction risk, maintainability under change, or evidence quality.",
        "required_evidence": [
            "thermo/simplifier rubric result",
            "largest/hottest modules reviewed",
            "concrete hotspots list with owners",
            "implementation phases for real blockers",
            "runtime complexity risks checked, including slow queries, expensive loops, N+1 calls, repeated network/API work, or unbounded scans where applicable",
            "product workflow complexity and state complexity reviewed where applicable",
            "architecture ownership and over-abstraction risks reviewed",
            "verification via lint, typecheck, tests, build, and runtime proof",
            "accepted exceptions recorded only with rationale and expiry",
        ],
    },
    "anti_slop_product_quality": {
        "title": "Anti-Slop And Product Quality",
        "standard": "The repo avoids placeholder/demo behavior, shallow copy, fake states, incoherent UX, and low-trust product surfaces.",
        "gate_caveat": "A passing anti-slop command only proves the configured static scan passed; it does not prove product-quality or domain-fit compliance.",
        "required_evidence": [
            "primary user workflows inspected",
            "placeholder/demo paths identified or ruled out",
            "copy and state quality reviewed",
            "product-specific quality risks documented",
        ],
    },
    "architecture_boundaries": {
        "title": "Architecture Boundaries",
        "standard": "Layering, dependency direction, ownership boundaries, and runtime contracts are explicit and enforced where practical.",
        "gate_caveat": "A passing architecture command does not prove the whole system has clean boundaries or low coupling.",
        "required_evidence": [
            "declared architecture boundaries",
            "known boundary violations or gaps",
            "dependency direction proof",
            "cross-layer risk and remediation plan",
        ],
    },
    "test_quality_value": {
        "title": "Test Quality And Test Value",
        "standard": "Tests protect behavior, contracts, regressions, data integrity, and critical workflows without brittle volume padding.",
        "gate_caveat": "A passing test command does not prove meaningful coverage, and a failing command does not identify which behavioral guarantees are missing.",
        "required_evidence": [
            "critical behavior map",
            "coverage of public contracts and regressions",
            "brittle or duplicated tests identified",
            "missing high-value tests scoped",
        ],
    },
    "ui_visual_runtime_verification": {
        "title": "UI Visual And Runtime Verification",
        "standard": "UI-bearing repos prove actual rendered behavior through local launch plus visual inspection, screenshots, browser/device automation, or simulator evidence appropriate to the platform.",
        "gate_caveat": "Passing UI lint, typecheck, component tests, or TMCP UI rubric review does not prove the interface renders correctly, is usable, or avoids visual regressions.",
        "required_evidence": [
            "UI surfaces classified as web, mobile, desktop, or none",
            "local launch command or accepted no-UI exception",
            "visual proof from browser automation, computer use, screenshots, Xcode simulator, or equivalent",
            "layout, interaction, loading, empty, and error states checked where applicable",
        ],
    },
    "dead_code": {
        "title": "Dead Code And Obsolete Surface",
        "standard": "Unused code, abandoned flags, stale paths, and obsolete tests are either removed or explicitly justified.",
        "gate_caveat": "Dead-code tooling can miss dynamic usage and cannot decide product ownership by itself.",
        "required_evidence": [
            "dead-code tool output or manual inventory",
            "dynamic-entry exceptions",
            "obsolete feature/test candidates",
            "safe removal or quarantine plan",
        ],
    },
    "security_secret_handling": {
        "title": "Security And Secret Handling",
        "standard": "Secrets, auth boundaries, protected data, unsafe logs, and security-sensitive workflows are reviewed beyond regex matches.",
        "gate_caveat": "A passing secret scan only proves configured patterns did not match; it does not prove security or privacy safety.",
        "required_evidence": [
            "secret scan results reviewed",
            "auth and protected-data boundaries checked",
            "unsafe logs or fixtures assessed",
            "accepted security exceptions recorded",
        ],
    },
    "dependency_risk": {
        "title": "Dependency And Supply-Chain Risk",
        "standard": "Dependencies, lockfiles, package-manager authority, vulnerabilities, and upgrade risks are understood and actively managed.",
        "gate_caveat": "A passing audit command does not prove supply-chain health, stale dependency posture, or package-manager consistency.",
        "required_evidence": [
            "canonical package manager identified",
            "audit findings triaged",
            "lockfile drift assessed",
            "upgrade or exception plan documented",
        ],
    },
    "truth_docs_accuracy": {
        "title": "Truth And Documentation Accuracy",
        "standard": "AGENTS, README, project truth, and adoption docs reflect the current runnable state and known blockers.",
        "gate_caveat": "File-presence checks prove documents exist, not that they are accurate.",
        "required_evidence": [
            "truth files compared to current repo state",
            "setup and quality commands verified",
            "known blockers documented",
            "accepted exceptions visible",
        ],
    },
    "ci_local_proof_integrity": {
        "title": "CI And Local Proof Integrity",
        "standard": "Remote CI or approved local replacement proof exercises the same meaningful gates required for adoption.",
        "gate_caveat": "CI file presence or a local proof wrapper does not prove release readiness unless underlying gates pass.",
        "required_evidence": [
            "CI or local replacement path identified",
            "required gate list tied to proof",
            "non-remote exception justified",
            "latest proof result and blockers recorded",
        ],
    },
    "release_rollback_readiness": {
        "title": "Release And Rollback Readiness",
        "standard": "Apps, packages, tools, and data/content repos have an explicit release path and a rollback or recovery story appropriate to their class.",
        "gate_caveat": "Passing local checks does not prove deployability, package versioning, migration safety, or rollback readiness.",
        "required_evidence": [
            "release or package command/result",
            "environment and migration readiness proof where applicable",
            "rollback/recovery notes or accepted no-release exception",
            "latest release blocker list",
        ],
    },
    "data_state_integrity": {
        "title": "Data And State Integrity",
        "standard": "Stateful repos prove migrations, seeds, queues, sync jobs, scraping, backfills, and data/content validators are safe, idempotent, and representative.",
        "gate_caveat": "Passing unit tests or build does not prove state transitions, migrations, external sync, or content/data correctness.",
        "required_evidence": [
            "stateful surfaces classified or no-state exception documented",
            "migration/seed/backfill/idempotency proof where applicable",
            "representative data/content validation result",
            "failure recovery or rollback behavior documented",
        ],
    },
    "observability_debuggability": {
        "title": "Observability And Debuggability",
        "standard": "The repo exposes enough logs, errors, health checks, diagnostics, or runbooks for another agent to debug realistic failures.",
        "gate_caveat": "A passing test suite does not prove failures will be diagnosable in local, preview, package, or device runtime.",
        "required_evidence": [
            "health check, structured logs, diagnostics, or runbook evidence",
            "critical failure paths named with observable signals",
            "unsafe logging or missing-context risks reviewed",
            "accepted observability gaps recorded with follow-up phase",
        ],
    },
}

ValidationResult = dict[str, Any]


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        loaded = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _relative(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _exists(repo_root: Path, relative_path: str) -> bool:
    return (repo_root / relative_path).exists()


def _matching_files(repo_root: Path, patterns: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(_relative(path, repo_root) for path in sorted(repo_root.glob(pattern)))
    return sorted(dict.fromkeys(matches))


def _package_scripts(repo_root: Path) -> dict[str, str]:
    package = _read_json(repo_root / "package.json")
    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {
        str(name): str(command)
        for name, command in scripts.items()
        if isinstance(name, str) and isinstance(command, str)
    }


def _pyproject_tools(repo_root: Path) -> dict[str, Any]:
    pyproject = _read_toml(repo_root / "pyproject.toml")
    tool = pyproject.get("tool")
    return tool if isinstance(tool, dict) else {}


def _quality_contract(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / ".aios-quality-gate.json")


def _declared_quality_gates(contract: dict[str, Any]) -> set[str]:
    gates: set[str] = set()
    for field in ("preCommitGates", "fullGates"):
        value = contract.get(field)
        if isinstance(value, list):
            gates.update(str(item) for item in value if isinstance(item, str) and item.strip())
    return gates


def _script_evidence(
    scripts: dict[str, str],
    gate_terms: tuple[str, ...],
) -> list[str]:
    evidence: list[str] = []
    for name, command in sorted(scripts.items()):
        haystack = f"{name} {command}".lower()
        if any(term in haystack for term in gate_terms):
            evidence.append(f"package.json:scripts.{name}")
    return evidence


def _gate_evidence(
    *,
    repo_root: Path,
    scripts: dict[str, str],
    pyproject_tools: dict[str, Any],
    contract_gates: set[str],
) -> dict[str, list[str]]:
    ci_files = _matching_files(
        repo_root,
        (
            ".github/workflows/*.yml",
            ".github/workflows/*.yaml",
            ".gitlab-ci.yml",
            ".circleci/config.yml",
        ),
    )
    evidence = {
        "install": [
            *_script_evidence(
                scripts,
                ("install", "frozen-lockfile", "frozen install", "uv sync", "make install"),
            ),
            *(".aios-quality-gate.json:install" for _ in [0] if "install" in contract_gates),
        ],
        "formatter": [
            *_script_evidence(scripts, ("format", "prettier", "ruff format")),
            *("pyproject.toml:tool.ruff" for _ in [0] if "ruff" in pyproject_tools),
        ],
        "lint": [
            *_script_evidence(scripts, ("lint", "eslint", "ruff check")),
            *("pyproject.toml:tool.ruff" for _ in [0] if "ruff" in pyproject_tools),
            *("eslint.config.js" for _ in [0] if _exists(repo_root, "eslint.config.js")),
        ],
        "typecheck": [
            *_script_evidence(scripts, ("typecheck", "tsc", "pyright", "basedpyright", "mypy")),
            *("tsconfig.json" for _ in [0] if _exists(repo_root, "tsconfig.json")),
            *("pyproject.toml:tool.basedpyright" for _ in [0] if "basedpyright" in pyproject_tools),
            *("pyproject.toml:tool.pyright" for _ in [0] if "pyright" in pyproject_tools),
        ],
        "tests": [
            *_script_evidence(scripts, ("test", "vitest", "jest", "pytest")),
            *("pyproject.toml:tool.pytest" for _ in [0] if "pytest" in pyproject_tools),
        ],
        "build": [
            *_script_evidence(scripts, ("build", "next build", "vite build", "tsup")),
            *(
                "pyproject.toml:build-system"
                for _ in [0]
                if _read_toml(repo_root / "pyproject.toml").get("build-system")
            ),
        ],
        "package": [
            *_script_evidence(scripts, ("package", "pack", "consumer", "smoke")),
            *(".aios-quality-gate.json:package" for _ in [0] if "package" in contract_gates),
        ],
        "validation": [
            *_script_evidence(scripts, ("validation", "validate")),
            *(".aios-quality-gate.json:validation" for _ in [0] if "validation" in contract_gates),
        ],
        "dead_code": [
            *_script_evidence(scripts, ("knip", "vulture", "dead-code", "dead_code")),
            *("knip.json" for _ in [0] if _exists(repo_root, "knip.json")),
            *("pyproject.toml:tool.vulture" for _ in [0] if "vulture" in pyproject_tools),
        ],
        "structural_scan": [
            *_script_evidence(scripts, ("ast-grep", "ast_grep", "anti-slop", "anti_slop")),
            *(".sgconfig.yml" for _ in [0] if _exists(repo_root, ".sgconfig.yml")),
            *("sgconfig.yml" for _ in [0] if _exists(repo_root, "sgconfig.yml")),
        ],
        "complexity_budget": [
            *_script_evidence(
                scripts,
                (
                    "complexity-budget",
                    "complexity_budget",
                    "complexity",
                    "big-o",
                    "bigo",
                    "performance",
                    "benchmark",
                    "bench",
                ),
            ),
            *(
                ".aios-quality-gate.json:complexity_budget"
                for _ in [0]
                if contract_gates
                & {
                    "complexity_budget",
                    "complexity-budget",
                    "performance_budget",
                    "performance-budget",
                }
            ),
        ],
        "secret_scan": [
            *_script_evidence(
                scripts,
                (
                    "secret-scan",
                    "secret_scan",
                    "secret",
                    "detect-secrets",
                    "gitleaks",
                    "trufflehog",
                ),
            ),
            *(
                ".aios-quality-gate.json:secret_scan"
                for _ in [0]
                if "secret_scan" in contract_gates
            ),
        ],
        "dependency_security": [
            *_script_evidence(
                scripts,
                (
                    "dependency-security",
                    "dependency_security",
                    "audit",
                    "snyk",
                    "osv",
                    "pip-audit",
                    "safety",
                ),
            ),
            *(
                ".aios-quality-gate.json:dependency_security"
                for _ in [0]
                if "dependency_security" in contract_gates
            ),
        ],
        "mobile_release": [
            *_script_evidence(
                scripts,
                ("mobile-release", "mobile_release", "xcodebuild", "fastlane", "gradle", "eas"),
            ),
            *(
                ".aios-quality-gate.json:mobile_release"
                for _ in [0]
                if "mobile_release" in contract_gates
            ),
        ],
        "e2e_smoke": [
            *_script_evidence(scripts, ("e2e", "smoke", "playwright", "cypress")),
            *(".aios-quality-gate.json:e2e_smoke" for _ in [0] if "e2e_smoke" in contract_gates),
        ],
        "runtime_smoke": [
            *_script_evidence(
                scripts,
                (
                    "runtime-smoke",
                    "runtime_smoke",
                    "smoke",
                    "healthcheck",
                    "preview",
                    "simulator",
                    "device",
                    "launch",
                    "cli:smoke",
                ),
            ),
            *(
                ".aios-quality-gate.json:runtime_smoke"
                for _ in [0]
                if "runtime_smoke" in contract_gates
            ),
        ],
        "pre_pr_readiness": [
            *_script_evidence(
                scripts,
                ("pre-pr", "pre_pr", "pre-pr-readiness", "pre_pr_readiness"),
            ),
            *(
                ".aios-quality-gate.json:pre_pr_readiness"
                for _ in [0]
                if "pre_pr_readiness" in contract_gates
            ),
        ],
        "release_rollback_readiness": [
            *_script_evidence(
                scripts,
                (
                    "release",
                    "rollback",
                    "deploy",
                    "version",
                    "migration",
                    "package",
                    "publish",
                ),
            ),
            *("docs/release.md" for _ in [0] if _exists(repo_root, "docs/release.md")),
            *("docs/rollback.md" for _ in [0] if _exists(repo_root, "docs/rollback.md")),
            *(
                ".aios-quality-gate.json:release_rollback_readiness"
                for _ in [0]
                if "release_rollback_readiness" in contract_gates
            ),
        ],
        "thermo_nuclear_simplification": [
            *_script_evidence(
                scripts,
                (
                    "thermo",
                    "thermo-nuclear",
                    "thermo_nuclear",
                    "complexity-simplification",
                    "simplification",
                ),
            ),
            *(
                ".aios-quality-gate.json:thermo_nuclear_simplification"
                for _ in [0]
                if "thermo_nuclear_simplification" in contract_gates
            ),
        ],
        "pre_cr": [".pre-cr.json"] if _exists(repo_root, ".pre-cr.json") else [],
        "anti_slop": [
            *_script_evidence(scripts, ("anti-slop", "anti_slop")),
            *(".aios-quality-gate.json:anti_slop" for _ in [0] if "anti_slop" in contract_gates),
        ],
        "data_state_integrity": [
            *_script_evidence(
                scripts,
                (
                    "db:",
                    "database",
                    "migration",
                    "migrate",
                    "seed",
                    "data",
                    "backfill",
                    "sync",
                    "scrape",
                    "content",
                    "state",
                ),
            ),
            *("prisma/schema.prisma" for _ in [0] if _exists(repo_root, "prisma/schema.prisma")),
            *("supabase/migrations" for _ in [0] if _exists(repo_root, "supabase/migrations")),
            *("migrations" for _ in [0] if _exists(repo_root, "migrations")),
            *(
                ".aios-quality-gate.json:data_state_integrity"
                for _ in [0]
                if "data_state_integrity" in contract_gates
            ),
        ],
        "observability_debuggability": [
            *_script_evidence(
                scripts,
                (
                    "healthcheck",
                    "health",
                    "observability",
                    "diagnostic",
                    "debug",
                    "logs",
                    "trace",
                    "monitor",
                ),
            ),
            *("docs/observability.md" for _ in [0] if _exists(repo_root, "docs/observability.md")),
            *("docs/debugging.md" for _ in [0] if _exists(repo_root, "docs/debugging.md")),
            *(
                ".aios-quality-gate.json:observability_debuggability"
                for _ in [0]
                if "observability_debuggability" in contract_gates
            ),
        ],
        "repo_truth": [
            *(
                ".tracker/PROJECT_TRUTH.md"
                for _ in [0]
                if _exists(repo_root, ".tracker/PROJECT_TRUTH.md")
            ),
            *("AGENTS.md" for _ in [0] if _exists(repo_root, "AGENTS.md")),
        ],
        "local_quality_contract": [".aios-quality-gate.json"]
        if _exists(repo_root, ".aios-quality-gate.json")
        else [],
        "ci": ci_files,
        "local_hook": [
            *(".husky/pre-commit" for _ in [0] if _exists(repo_root, ".husky/pre-commit")),
            *(
                ".pre-commit-config.yaml"
                for _ in [0]
                if _exists(repo_root, ".pre-commit-config.yaml")
            ),
            *(".git/hooks/pre-commit" for _ in [0] if _exists(repo_root, ".git/hooks/pre-commit")),
        ],
    }
    return {gate_id: sorted(dict.fromkeys(items)) for gate_id, items in evidence.items()}


def _project_kind(repo_root: Path) -> str:
    has_package = _exists(repo_root, "package.json")
    has_pyproject = _exists(repo_root, "pyproject.toml")
    has_tsconfig = _exists(repo_root, "tsconfig.json")
    if has_package and has_pyproject:
        return "mixed"
    if has_package and has_tsconfig:
        return "typescript_app"
    if has_package:
        return "javascript_project"
    if has_pyproject:
        return "python_project"
    return "unknown"


def _load_quality_pipeline_config(path: Path = QUALITY_PIPELINE_CONFIG_PATH) -> dict[str, Any]:
    if path.exists():
        return _read_json(path)
    workspace_config = Path.cwd() / "config" / "quality-pipeline.json"
    if workspace_config.exists():
        return _read_json(workspace_config)
    return {}


def _quality_profile_match_keys(repo_root: Path, contract: dict[str, Any]) -> set[str]:
    keys = {repo_root.name, repo_root.name.lower(), str(repo_root), str(repo_root).lower()}
    project_id = contract.get("projectId")
    if isinstance(project_id, str) and project_id.strip():
        keys.add(project_id.strip())
        keys.add(project_id.strip().lower())
    return keys


def _quality_pipeline_project_profile(repo_root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    config = _load_quality_pipeline_config()
    standard = config.get("standard")
    standard = standard if isinstance(standard, dict) else {}
    projects = config.get("projects")
    projects = projects if isinstance(projects, list) else []
    keys = _quality_profile_match_keys(repo_root, contract)
    selected: dict[str, Any] = {}
    for row in projects:
        if not isinstance(row, dict):
            continue
        project_id = str(row.get("project_id", "")).strip()
        if project_id in keys or project_id.lower() in keys:
            selected = row
            break
    classes = standard.get("classes")
    classes = classes if isinstance(classes, dict) else {}
    repo_class = str(selected.get("repo_class", "")).strip() if selected else ""
    class_config = classes.get(repo_class)
    class_config = class_config if isinstance(class_config, dict) else {}
    gates = selected.get("gates") if selected else {}
    gates = gates if isinstance(gates, dict) else {}
    required_gates = class_config.get("required_gates")
    if not isinstance(required_gates, list):
        required_gates = []
    applies_to = selected.get("applies_to") if selected else []
    applies_to = applies_to if isinstance(applies_to, list) else []
    profile_status = "matched" if selected else "not_found"
    return {
        "status": profile_status,
        "project_id": selected.get("project_id", "") if selected else "",
        "repo_class": repo_class or None,
        "class_label": class_config.get("label"),
        "applies_to": [str(item) for item in applies_to],
        "required_gates": [str(item) for item in required_gates],
        "configured_gates": sorted(str(key) for key in gates),
        "gate_commands": {
            str(key): {
                "command": str(value.get("command", "")) if isinstance(value, dict) else "",
                "working_directory": (
                    str(value.get("working_directory", "")) if isinstance(value, dict) else ""
                ),
            }
            for key, value in gates.items()
        },
        "strict_readiness_status": selected.get("strict_readiness_status") if selected else None,
        "maturation_blockers": [
            str(item) for item in selected.get("maturation_blockers", []) if isinstance(item, str)
        ]
        if selected
        else [],
        "non_remote_ci_exception": selected.get("non_remote_ci_exception") if selected else None,
        "readiness_note": class_config.get("readiness_note"),
    }


def _classification_evidence(
    repo_root: Path, project_kind: str, profile: dict[str, Any]
) -> dict[str, Any]:
    signals: list[str] = []
    if _exists(repo_root, "package.json"):
        signals.append("package.json")
    if _exists(repo_root, "tsconfig.json"):
        signals.append("tsconfig.json")
    if _exists(repo_root, "pyproject.toml"):
        signals.append("pyproject.toml")
    if _exists(repo_root, "Package.swift"):
        signals.append("Package.swift")
    if _exists(repo_root, "ios") or _matching_files(repo_root, ("*.xcodeproj", "*.xcworkspace")):
        signals.append("ios/xcode")
    profile_status = str(profile.get("status", "not_found"))
    confidence = "high" if profile_status == "matched" else "medium" if signals else "low"
    return {
        "project_kind": project_kind,
        "selected_profile": profile.get("repo_class"),
        "profile_status": profile_status,
        "confidence": confidence,
        "signals": signals,
        "reasoning": (
            "Matched AIOS quality-pipeline profile and repo-local technology signals."
            if profile_status == "matched"
            else "No AIOS quality-pipeline project profile matched; classification uses repo-local signals only."
        ),
    }


def _visual_proof_route(project_kind: str, profile: dict[str, Any]) -> dict[str, Any]:
    applies_to = {str(item) for item in profile.get("applies_to", []) if isinstance(item, str)}
    repo_class = str(profile.get("repo_class") or "")
    has_ui = bool(
        applies_to
        & {
            "typescript_app",
            "production_app",
            "public_web",
            "production_public_web_app",
            "mobile_app",
        }
    ) or project_kind in {"typescript_app", "javascript_project"}
    if "mobile_app" in applies_to or repo_class == "mobile_app":
        route = "xcode_or_mobile_simulator"
        commands = [
            "Run the native/mobile build or simulator launch command.",
            "Capture simulator/device screenshots for primary flows and failure states.",
        ]
    elif has_ui:
        route = "local_web_launch_browser_visual"
        commands = [
            "Run the local dev or preview server.",
            "Use browser automation, screenshots, or computer-use inspection for primary flows.",
        ]
    else:
        route = "no_ui_exception"
        commands = ["Record an explicit no-UI exception for this rubric."]
    return {
        "ui_applicable": has_ui,
        "route": route,
        "recommended_evidence": commands,
        "accepted_tools": [
            "browser automation",
            "screenshots",
            "computer use",
            "Xcode simulator",
            "platform-equivalent runtime proof",
        ],
    }


def _gate_profile_keys(gate_id: str) -> tuple[str, ...]:
    return (gate_id, *QUALITY_PROFILE_GATE_ALIASES.get(gate_id, ()))


def _looks_like_placeholder_command(command: str) -> bool:
    normalized = " ".join(command.strip().lower().split())
    return normalized in {"", "true", ":", "exit 0", "echo ok", "echo pass", "echo todo"}


def _quality_profile_gate_command(
    quality_profile: dict[str, Any],
    gate_id: str,
) -> tuple[str, dict[str, str]] | None:
    gate_commands = quality_profile.get("gate_commands")
    if not isinstance(gate_commands, dict):
        return None
    for profile_gate_id in _gate_profile_keys(gate_id):
        command = gate_commands.get(profile_gate_id)
        if not isinstance(command, dict):
            continue
        raw_command = str(command.get("command", "")).strip()
        if _looks_like_placeholder_command(raw_command):
            continue
        return profile_gate_id, {
            "command": raw_command,
            "working_directory": str(command.get("working_directory", "")).strip(),
        }
    return None


def _add_quality_profile_gate_evidence(
    gate_evidence: dict[str, list[str]],
    quality_profile: dict[str, Any],
) -> dict[str, list[str]]:
    merged = {gate_id: list(items) for gate_id, items in gate_evidence.items()}
    for gate_id in CORE_GATE_IDS:
        command = _quality_profile_gate_command(quality_profile, gate_id)
        if command is None:
            continue
        profile_gate_id, command_payload = command
        evidence = f"quality-pipeline:{profile_gate_id}:{command_payload['command']}"
        merged.setdefault(gate_id, [])
        if evidence not in merged[gate_id]:
            merged[gate_id].append(evidence)
    return {gate_id: sorted(dict.fromkeys(items)) for gate_id, items in merged.items()}


def _gate_skip_reason(gate_id: str, quality_profile: dict[str, Any]) -> str | None:
    repo_class = str(quality_profile.get("repo_class") or "")
    applies_to = {
        str(item) for item in quality_profile.get("applies_to", []) if isinstance(item, str)
    }
    if (
        gate_id == "mobile_release"
        and repo_class != "mobile_app"
        and "mobile_app" not in applies_to
    ):
        return "Skipped for non-mobile repo class; use UI/runtime proof and e2e smoke instead."
    if gate_id == "local_hook":
        return (
            "Optional local developer hook; CI or approved local replacement proof is sufficient."
        )
    return None


def scan_repo_gate_facts(repo_root: Path, *, run_id: str) -> dict[str, Any]:
    resolved_root = repo_root.expanduser().resolve()
    scripts = _package_scripts(resolved_root)
    pyproject_tools = _pyproject_tools(resolved_root)
    contract = _quality_contract(resolved_root)
    project_kind = _project_kind(resolved_root)
    quality_profile = _quality_pipeline_project_profile(resolved_root, contract)
    contract_gates = _declared_quality_gates(contract)
    gate_evidence = _gate_evidence(
        repo_root=resolved_root,
        scripts=scripts,
        pyproject_tools=pyproject_tools,
        contract_gates=contract_gates,
    )
    gate_evidence = _add_quality_profile_gate_evidence(gate_evidence, quality_profile)
    return {
        "schema": REPO_SCAN_SCHEMA,
        "run_id": run_id,
        "repo_path": str(resolved_root),
        "project_kind": project_kind,
        "classification": _classification_evidence(resolved_root, project_kind, quality_profile),
        "quality_profile": quality_profile,
        "visual_proof_route": _visual_proof_route(project_kind, quality_profile),
        "files_present": _matching_files(
            resolved_root,
            (
                "package.json",
                "pnpm-lock.yaml",
                "pyproject.toml",
                "uv.lock",
                "tsconfig.json",
                ".pre-cr.json",
                ".aios-quality-gate.json",
                ".tracker/PROJECT_TRUTH.md",
                "AGENTS.md",
                "knip.json",
                "docs/release.md",
                "docs/rollback.md",
                "docs/observability.md",
                "docs/debugging.md",
                "prisma/schema.prisma",
                "supabase/migrations",
                "migrations",
                ".sgconfig.yml",
                "sgconfig.yml",
            ),
        ),
        "package_scripts": scripts,
        "pyproject_tools": sorted(str(key) for key in pyproject_tools),
        "quality_contract": {
            "present": bool(contract),
            "project_id": str(contract.get("projectId", "")) if contract else "",
            "pre_commit_gates": [
                str(item) for item in contract.get("preCommitGates", []) if isinstance(item, str)
            ],
            "full_gates": [
                str(item) for item in contract.get("fullGates", []) if isinstance(item, str)
            ],
        },
        "gate_evidence": gate_evidence,
    }


def _gate_status(gate_id: str, evidence: list[str]) -> str:
    if not evidence:
        return "absent"
    if any(item.startswith("quality-pipeline:") for item in evidence):
        return "present"
    if gate_id in {"formatter", "lint", "typecheck", "tests", "build"} and all(
        not item.startswith("package.json:scripts.") for item in evidence
    ):
        return "partial"
    if gate_id == "repo_truth" and ".tracker/PROJECT_TRUTH.md" not in evidence:
        return "partial"
    return "present"


def _gate_maturity_for_status(status: str, enforcement: str) -> str:
    if status == "skipped":
        return "not_applicable"
    return _maturity(status, enforcement)


def _gate_enforcement(gate_id: str, scan: dict[str, Any]) -> str:
    contract_gate_aliases = {
        "install": {"install"},
        "tests": {"tests", "test", "test_quality"},
        "package": {"package", "package_smoke", "consumer_smoke"},
        "validation": {"validation", "validate"},
        "structural_scan": {"structural_scan", "architecture", "thermo_nuclear_simplification"},
        "complexity_budget": {
            "complexity_budget",
            "complexity-budget",
            "performance_budget",
            "performance-budget",
        },
        "secret_scan": {"secret_scan", "secret-scan"},
        "dependency_security": {"dependency_security", "dependency-security"},
        "mobile_release": {"mobile_release", "mobile-release"},
        "e2e_smoke": {"e2e_smoke", "e2e-smoke", "smoke"},
        "runtime_smoke": {"runtime_smoke", "runtime-smoke", "smoke"},
        "pre_pr_readiness": {"pre_pr_readiness", "pre-pr-readiness"},
        "release_rollback_readiness": {
            "release_rollback_readiness",
            "release-rollback-readiness",
            "release_readiness",
            "release-readiness",
        },
        "thermo_nuclear_simplification": {
            "thermo_nuclear_simplification",
            "thermo-nuclear-simplification",
        },
        "pre_cr": {"pre_cr"},
        "anti_slop": {"anti_slop"},
        "data_state_integrity": {"data_state_integrity", "data-state-integrity"},
        "observability_debuggability": {
            "observability_debuggability",
            "observability-debuggability",
        },
    }
    contract = scan.get("quality_contract")
    declared_gates: set[str] = set()
    if isinstance(contract, dict):
        declared_gates.update(
            str(item) for item in contract.get("pre_commit_gates", []) if isinstance(item, str)
        )
        declared_gates.update(
            str(item) for item in contract.get("full_gates", []) if isinstance(item, str)
        )
    declared_aliases = contract_gate_aliases.get(gate_id, {gate_id})
    if declared_gates & declared_aliases:
        return "hard"
    quality_profile = scan.get("quality_profile")
    if isinstance(quality_profile, dict) and _quality_profile_gate_command(
        quality_profile, gate_id
    ):
        return "soft"
    gate_evidence = scan.get("gate_evidence")
    if isinstance(gate_evidence, dict):
        local_hook_evidence = gate_evidence.get("local_hook")
        ci_evidence = gate_evidence.get("ci")
        if (
            gate_id == "local_hook"
            and isinstance(local_hook_evidence, list)
            and local_hook_evidence
        ):
            return "soft"
        if gate_id == "ci" and isinstance(ci_evidence, list) and ci_evidence:
            return "soft"
    return "not_enforced"


def _maturity(status: str, enforcement: str) -> str:
    if status == "present" and enforcement in {"hard", "soft"}:
        return "enforceable"
    if status == "present":
        return "baseline_first"
    if status == "partial":
        return "risky_to_enforce_now"
    return "baseline_first"


def build_gate_matrix(*, scan: dict[str, Any], run_id: str) -> dict[str, Any]:
    raw_evidence = scan.get("gate_evidence")
    gate_evidence = raw_evidence if isinstance(raw_evidence, dict) else {}
    quality_profile = scan.get("quality_profile")
    quality_profile = quality_profile if isinstance(quality_profile, dict) else {}
    required_profile_gates = {
        str(item) for item in quality_profile.get("required_gates", []) if isinstance(item, str)
    }
    gates: list[dict[str, Any]] = []
    for gate_id in CORE_GATE_IDS:
        evidence = gate_evidence.get(gate_id)
        evidence_items = [str(item) for item in evidence] if isinstance(evidence, list) else []
        profile_command = _quality_profile_gate_command(quality_profile, gate_id)
        skip_reason = _gate_skip_reason(gate_id, quality_profile)
        status = _gate_status(gate_id, evidence_items)
        enforcement = _gate_enforcement(gate_id, scan)
        if status == "absent" and skip_reason:
            status = "skipped"
            enforcement = "accepted_exception"
        gates.append(
            {
                "id": gate_id,
                "label": GATE_LABELS[gate_id],
                "status": status,
                "enforcement": enforcement,
                "maturity": _gate_maturity_for_status(status, enforcement),
                "evidence": evidence_items,
                "skip_reason": skip_reason,
                "quality_profile_required": any(
                    profile_gate_id in required_profile_gates
                    for profile_gate_id in _gate_profile_keys(gate_id)
                ),
                "quality_profile_gate_key": profile_command[0] if profile_command else None,
                "quality_profile_command": profile_command[1] if profile_command else {},
                "adoption_action": _adoption_action(gate_id, status, enforcement),
            }
        )
    summary = {
        "present": len([gate for gate in gates if gate["status"] == "present"]),
        "partial": len([gate for gate in gates if gate["status"] == "partial"]),
        "absent": len([gate for gate in gates if gate["status"] == "absent"]),
        "skipped": len([gate for gate in gates if gate["status"] == "skipped"]),
        "enforceable": len([gate for gate in gates if gate["maturity"] == "enforceable"]),
        "risky_to_enforce_now": len(
            [gate for gate in gates if gate["maturity"] == "risky_to_enforce_now"]
        ),
    }
    return {
        "schema": GATE_MATRIX_SCHEMA,
        "run_id": run_id,
        "repo_path": scan.get("repo_path", ""),
        "project_kind": scan.get("project_kind", "unknown"),
        "classification": scan.get("classification", {}),
        "quality_profile": scan.get("quality_profile", {}),
        "visual_proof_route": scan.get("visual_proof_route", {}),
        "gates": gates,
        "summary": summary,
    }


def gate_adoption_output_dir(repo_root: Path, run_id: str) -> Path:
    return repo_root / AIOS_BACKFILL_DIR_NAME / "gate-adoption" / run_id


def _rubric_detail_path(run_id: str, rubric_id: str, doc_kind: str, extension: str) -> str:
    return (
        f"{AIOS_BACKFILL_DIR_NAME}/gate-adoption/{run_id}/rubrics/"
        f"{rubric_id}.{doc_kind}.{extension}"
    )


def _git_info_exclude_path(repo_root: Path) -> Path | None:
    git_path = repo_root / ".git"
    if git_path.is_dir():
        return git_path / "info" / "exclude"
    if not git_path.is_file():
        return None
    try:
        raw = git_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    prefix = "gitdir:"
    if not raw.startswith(prefix):
        return None
    git_dir = Path(raw.removeprefix(prefix).strip())
    if not git_dir.is_absolute():
        git_dir = (repo_root / git_dir).resolve()
    return git_dir / "info" / "exclude"


def ensure_aios_backfill_gitignored(repo_root: Path) -> Path | None:
    exclude_path = _git_info_exclude_path(repo_root)
    if exclude_path is None:
        return None
    ignore_rule = f"{AIOS_BACKFILL_DIR_NAME}/"
    existing = ""
    if exclude_path.exists():
        existing = exclude_path.read_text(encoding="utf-8", errors="replace")
        if any(line.strip() == ignore_rule for line in existing.splitlines()):
            return exclude_path
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if not existing or existing.endswith("\n") else "\n"
    exclude_path.write_text(f"{existing}{separator}{ignore_rule}\n", encoding="utf-8")
    return exclude_path


def _gate_phase_cluster(gate_id: str) -> str:
    if gate_id in {
        "install",
        "formatter",
        "lint",
        "typecheck",
        "tests",
        "build",
        "package",
        "validation",
        "mobile_release",
        "e2e_smoke",
        "runtime_smoke",
    }:
        return "package_and_runtime_quality"
    if gate_id in {
        "dead_code",
        "structural_scan",
        "complexity_budget",
        "thermo_nuclear_simplification",
        "anti_slop",
    }:
        return "maintainability_and_product_quality"
    if gate_id in {
        "data_state_integrity",
        "observability_debuggability",
        "release_rollback_readiness",
    }:
        return "release_runtime_and_state_integrity"
    if gate_id in {
        "repo_truth",
        "local_quality_contract",
        "pre_cr",
        "pre_pr_readiness",
        "ci",
        "local_hook",
    }:
        return "adoption_proof_and_truth"
    return "security_and_dependency_risk"


def _tmcp_relevant_terms(gate_matrix: dict[str, Any]) -> set[str]:
    terms = {
        "adoption",
        "quality",
        "rubric",
        "evidence",
        "verification",
        "complexity",
        "architecture",
        "ui",
        "visual",
        "runtime",
        "browser",
        "xcode",
        "simulator",
        "release",
        "rollback",
        "state",
        "data",
        "observability",
        "debugging",
        "test",
        "security",
        "dependency",
        "anti-slop",
        "truth",
        "ci",
    }
    gates = gate_matrix.get("gates")
    if isinstance(gates, list):
        for gate in gates:
            if not isinstance(gate, dict):
                continue
            terms.add(str(gate.get("id", "")).replace("_", "-"))
            terms.add(str(gate.get("label", "")).lower())
    return {term for term in terms if term}


def _gate_rows_by_id(gate_matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(gate.get("id", "")): gate
        for gate in _as_dict_list(gate_matrix.get("gates"))
        if str(gate.get("id", "")).strip()
    }


def _scan_files_present(scan: dict[str, Any]) -> list[str]:
    return _as_string_list(scan.get("files_present"))


def _scan_package_scripts(scan: dict[str, Any]) -> dict[str, str]:
    scripts = scan.get("package_scripts")
    if not isinstance(scripts, dict):
        return {}
    return {
        str(name): str(command)
        for name, command in scripts.items()
        if isinstance(name, str) and isinstance(command, str)
    }


def _gate_evidence_items(
    gates_by_id: dict[str, dict[str, Any]], gate_ids: tuple[str, ...]
) -> list[str]:
    evidence: list[str] = []
    for gate_id in gate_ids:
        gate = gates_by_id.get(gate_id, {})
        for item in _as_string_list(gate.get("evidence")):
            evidence.append(f"gate:{gate_id}:{item}")
        status = str(gate.get("status", "")).strip()
        enforcement = str(gate.get("enforcement", "")).strip()
        if status:
            evidence.append(f"gate:{gate_id}:status={status}")
        if enforcement:
            evidence.append(f"gate:{gate_id}:enforcement={enforcement}")
    return sorted(dict.fromkeys(evidence))


def _broad_known_evidence(
    rubric_id: str,
    *,
    scan: dict[str, Any],
    gate_matrix: dict[str, Any],
) -> list[str]:
    files = _scan_files_present(scan)
    scripts = _scan_package_scripts(scan)
    gates_by_id = _gate_rows_by_id(gate_matrix)
    classification = scan.get("classification")
    classification = classification if isinstance(classification, dict) else {}
    quality_profile = scan.get("quality_profile")
    quality_profile = quality_profile if isinstance(quality_profile, dict) else {}
    visual_route = scan.get("visual_proof_route")
    visual_route = visual_route if isinstance(visual_route, dict) else {}
    evidence_by_rubric = {
        "build_package_integrity": [
            *_gate_evidence_items(gates_by_id, ("build", "package", "install")),
            *(
                f"package.json:scripts.{name}"
                for name, command in sorted(scripts.items())
                if any(term in f"{name} {command}".lower() for term in ("build", "pack"))
            ),
        ],
        "runtime_smoke_integrity": [
            *_gate_evidence_items(gates_by_id, ("runtime_smoke", "e2e_smoke", "mobile_release")),
            *(
                f"package.json:scripts.{name}"
                for name, command in sorted(scripts.items())
                if any(
                    term in f"{name} {command}".lower()
                    for term in ("smoke", "playwright", "cypress", "simulator", "launch")
                )
            ),
        ],
        "complexity_simplification": [
            *_gate_evidence_items(
                gates_by_id,
                ("complexity_budget", "thermo_nuclear_simplification", "structural_scan"),
            ),
            *(
                f"package.json:scripts.{name}"
                for name, command in sorted(scripts.items())
                if any(
                    term in f"{name} {command}".lower()
                    for term in ("complex", "thermo", "bench", "perf")
                )
            ),
        ],
        "anti_slop_product_quality": [
            *_gate_evidence_items(gates_by_id, ("anti_slop", "structural_scan")),
            *(
                f"package.json:scripts.{name}"
                for name, command in sorted(scripts.items())
                if "anti-slop" in f"{name} {command}".lower()
                or "anti_slop" in f"{name} {command}".lower()
            ),
        ],
        "architecture_boundaries": [
            *_gate_evidence_items(gates_by_id, ("structural_scan", "pre_cr")),
            *(
                item
                for item in files
                if item in {"tsconfig.json", "pyproject.toml", ".pre-cr.json"}
            ),
        ],
        "test_quality_value": [
            *_gate_evidence_items(gates_by_id, ("tests", "e2e_smoke", "validation")),
            *(
                f"package.json:scripts.{name}"
                for name, command in sorted(scripts.items())
                if any(
                    term in f"{name} {command}".lower()
                    for term in ("test", "vitest", "jest", "pytest", "playwright")
                )
            ),
        ],
        "ui_visual_runtime_verification": [
            f"visual-proof-route:{visual_route.get('route', 'unknown')}",
            f"visual-proof-ui-applicable:{visual_route.get('ui_applicable', False)}",
            *_gate_evidence_items(gates_by_id, ("build", "e2e_smoke")),
        ],
        "dead_code": [
            *_gate_evidence_items(gates_by_id, ("dead_code",)),
            *(item for item in files if item in {"knip.json", "pyproject.toml"}),
        ],
        "security_secret_handling": [
            *_gate_evidence_items(gates_by_id, ("secret_scan",)),
            *(
                f"package.json:scripts.{name}"
                for name, command in sorted(scripts.items())
                if "secret" in f"{name} {command}".lower()
            ),
        ],
        "dependency_risk": [
            *_gate_evidence_items(gates_by_id, ("dependency_security", "install")),
            *(
                item
                for item in files
                if item in {"package.json", "pnpm-lock.yaml", "uv.lock", "pyproject.toml"}
            ),
        ],
        "truth_docs_accuracy": [
            *_gate_evidence_items(gates_by_id, ("repo_truth",)),
            *(item for item in files if item in {"AGENTS.md", ".tracker/PROJECT_TRUTH.md"}),
        ],
        "ci_local_proof_integrity": [
            *_gate_evidence_items(gates_by_id, ("ci", "local_hook", "pre_pr_readiness")),
            f"quality-profile:non_remote_ci_exception={quality_profile.get('non_remote_ci_exception')}",
        ],
        "release_rollback_readiness": [
            *_gate_evidence_items(gates_by_id, ("release_rollback_readiness", "build", "package")),
            *(item for item in files if item in {"docs/release.md", "docs/rollback.md"}),
        ],
        "data_state_integrity": [
            *_gate_evidence_items(gates_by_id, ("data_state_integrity", "validation")),
            *(
                item
                for item in files
                if item in {"prisma/schema.prisma", "supabase/migrations", "migrations"}
            ),
        ],
        "observability_debuggability": [
            *_gate_evidence_items(gates_by_id, ("observability_debuggability",)),
            *(item for item in files if item in {"docs/observability.md", "docs/debugging.md"}),
        ],
    }
    evidence = [item for item in evidence_by_rubric.get(rubric_id, []) if str(item).strip()]
    evidence.extend(
        [
            f"classification:project_kind={scan.get('project_kind', 'unknown')}",
            f"classification:profile_status={classification.get('profile_status', 'unknown')}",
            f"classification:selected_profile={classification.get('selected_profile', None)}",
        ]
    )
    if not evidence:
        evidence.append(f"repo-scan:{rubric_id}:no matching local evidence found")
    return sorted(dict.fromkeys(str(item) for item in evidence if str(item).strip()))


def _broad_root_causes(
    rubric_id: str,
    known_evidence: list[str],
    definition: dict[str, Any],
) -> list[str]:
    title = str(definition.get("title", rubric_id))
    if any("status=absent" in item for item in known_evidence):
        return [
            f"{title} has at least one related gate with absent scan evidence.",
            "The generated audit must turn that absence into a scoped implementation phase or accepted exception.",
        ]
    if any("enforcement=not_enforced" in item for item in known_evidence):
        return [
            f"{title} has related evidence, but at least one related gate is not enforced.",
            "The implementation phase should decide whether to add enforcement, document a local replacement, or record an accepted exception.",
        ]
    return [
        f"{title} has repo-specific scan evidence attached.",
        "The remaining implementation work is to verify the evidence with fresh command/runtime proof before final certification.",
    ]


def _broad_missing_proof(rubric_id: str, known_evidence: list[str]) -> list[str]:
    missing: list[str] = []
    if any("status=absent" in item for item in known_evidence):
        missing.append("One or more related gates are absent and need implementation proof.")
    if any("enforcement=not_enforced" in item for item in known_evidence):
        missing.append(
            "One or more related gates need enforcement or an approved local replacement."
        )
    if rubric_id == "ui_visual_runtime_verification":
        missing.append(
            "Attach fresh screenshot/browser/device evidence before final certification."
        )
    if not missing:
        missing.append("Attach latest run output or accepted exception before final certification.")
    return missing


def _broad_blockers(known_evidence: list[str]) -> list[str]:
    blockers: list[str] = []
    if any("status=absent" in item for item in known_evidence):
        blockers.append("One or more related gates are absent in the generated scan.")
    if any("enforcement=not_enforced" in item for item in known_evidence):
        blockers.append("One or more related gates are not tied to hard/soft enforcement.")
    return blockers


def _gate_missing_proof(gate: dict[str, Any], known_evidence: list[str]) -> list[str]:
    missing: list[str] = []
    gate_id = str(gate.get("id", "unknown"))
    status = str(gate.get("status", "unknown"))
    enforcement = str(gate.get("enforcement", "unknown"))
    if status == "skipped":
        return [
            "No implementation proof required for this gate because it is explicitly skipped for this repo class."
        ]
    if status != "present":
        missing.append(f"Gate status is `{status}`; add command/evidence or record an exception.")
    if enforcement not in {"hard", "soft"}:
        missing.append(f"Gate enforcement is `{enforcement}`; add AIOS/CI/local proof linkage.")
    if not any(item.startswith("quality-pipeline:") for item in known_evidence):
        missing.append("Latest AIOS quality-pipeline command/result is not attached.")
    if gate_id in STRICT_CLEARANCE_GATE_IDS:
        missing.append(
            "Inherited baseline failures are remediation scope for this gate; attach a full passing command result before adoption-ready certification."
        )
    if not missing:
        missing.append("Attach latest passing command output before final certification.")
    return missing


def _gate_root_causes(gate: dict[str, Any], known_evidence: list[str]) -> list[str]:
    gate_id = str(gate.get("id", "unknown"))
    status = str(gate.get("status", "unknown"))
    enforcement = str(gate.get("enforcement", "unknown"))
    skip_reason = str(gate.get("skip_reason", "")).strip()
    causes: list[str] = []
    if status == "skipped":
        return [
            f"`{gate_id}` is intentionally skipped for this adoption profile.",
            skip_reason or "The gate is not applicable to this repo class.",
        ]
    if status == "absent":
        causes.append(
            f"The generated scan found no usable `{gate_id}` gate evidence in local scripts, AIOS profile commands, CI, hooks, or contract files."
        )
    elif status == "partial":
        causes.append(
            f"The generated scan found partial `{gate_id}` evidence, but not a complete repo-local command/proof surface."
        )
    else:
        causes.append(
            f"The generated scan found `{gate_id}` evidence: {', '.join(known_evidence[:3])}."
        )
    if enforcement not in {"hard", "soft"}:
        causes.append(f"`{gate_id}` is not linked to hard or soft enforcement yet.")
    else:
        causes.append(
            f"`{gate_id}` is linked to `{enforcement}` enforcement and needs fresh pass/fail proof."
        )
    return causes


def _gate_affected_files_or_scripts(gate: dict[str, Any], known_evidence: list[str]) -> list[str]:
    gate_id = str(gate.get("id", "unknown"))
    affected = [item for item in known_evidence if not item.startswith("gate:")]
    if affected:
        return sorted(dict.fromkeys(affected))
    guidance = GATE_SETUP_GUIDANCE.get(gate_id)
    if isinstance(guidance, dict):
        files = _as_string_list(guidance.get("files"))
        if files:
            return files
    if str(gate.get("status", "")) == "skipped":
        return [f"adoption-profile:{gate_id}:accepted-skip"]
    return [
        f"package.json:scripts (add or verify `{gate_id}` command when applicable)",
        f"AIOS quality profile for `{gate_id}`",
        ".aios-quality-gate.json or CI/local replacement proof",
    ]


def _gate_setup_actions(gate: dict[str, Any]) -> list[str]:
    gate_id = str(gate.get("id", "unknown"))
    status = str(gate.get("status", "unknown"))
    if status == "skipped":
        return [
            f"Keep `{gate_id}` documented as an accepted skip for this repo class.",
            "Revisit this exception only if the repo class changes.",
        ]
    guidance = GATE_SETUP_GUIDANCE.get(gate_id)
    if not isinstance(guidance, dict):
        return []
    actions = _as_string_list(guidance.get("actions"))
    commands = _as_string_list(guidance.get("commands"))
    if commands and status != "present":
        actions.append("Evaluate these candidate commands before adding one to the repo contract:")
        actions.extend(f"`{command}`" for command in commands)
    return actions


def _gate_accepted_exceptions(gate: dict[str, Any]) -> list[str]:
    if str(gate.get("status", "")) != "skipped":
        return []
    reason = str(gate.get("skip_reason", "")).strip()
    return [reason or "Gate is explicitly skipped for this repo class by the adoption workflow."]


def _tmcp_source_score(packet: dict[str, Any], relevant_terms: set[str]) -> dict[str, Any]:
    selected_nodes = [str(node) for node in packet.get("selected_nodes", [])]
    source_skill_nodes = [
        item for item in packet.get("source_skill_nodes", []) if isinstance(item, dict)
    ]
    source_hashes = packet.get("source_hashes")
    behavior_atoms = [str(atom) for atom in packet.get("behavior_atoms", [])]
    graph_metadata = packet.get("graph_metadata")
    graph_metadata = graph_metadata if isinstance(graph_metadata, dict) else {}
    warnings = [str(item) for item in graph_metadata.get("warnings", []) if str(item)]
    candidate_scores = packet.get("candidate_scores")
    candidate_scores = candidate_scores if isinstance(candidate_scores, dict) else {}
    source_scores = candidate_scores.get("source_skills")
    source_scores = source_scores if isinstance(source_scores, dict) else {}
    best_source_score = max(
        (float(score) for score in source_scores.values() if isinstance(score, (int, float))),
        default=0.0,
    )
    source_text = " ".join(
        [
            *selected_nodes,
            *(str(item.get("id", "")) for item in source_skill_nodes),
            *(str(item.get("node", "")) for item in source_skill_nodes),
            *behavior_atoms,
        ]
    ).casefold()
    matched_terms = sorted(term for term in relevant_terms if term.casefold() in source_text)
    source_hash_count = len(source_hashes) if isinstance(source_hashes, dict) else 0
    score = 0
    if source_skill_nodes:
        score += min(4, len(source_skill_nodes) * 2)
    if source_hash_count:
        score += min(2, source_hash_count)
    if matched_terms:
        score += min(3, len(matched_terms))
    if best_source_score >= 4:
        score += 2
    if warnings:
        score -= 2
    return {
        "score": max(score, 0),
        "source_skill_count": len(source_skill_nodes),
        "source_hash_count": source_hash_count,
        "matched_terms": matched_terms,
        "best_source_score": best_source_score,
        "warnings": warnings,
        "selected_nodes": selected_nodes,
        "source_skill_nodes": source_skill_nodes,
        "behavior_atoms": behavior_atoms,
    }


def build_tmcp_expert_enrichment(
    *,
    scan: dict[str, Any],
    gate_matrix: dict[str, Any],
    run_id: str,
    skills_library_path: Path | None = None,
    tmcp_compiler: TmcpCompiler | None = None,
    default_skills_library: Path | None = None,
    tmcp_domain: str = "repo_quality_certifier",
) -> dict[str, Any]:
    repo_path = str(gate_matrix.get("repo_path") or scan.get("repo_path") or "")
    project_kind = str(gate_matrix.get("project_kind") or scan.get("project_kind") or "unknown")
    objective = (
        "Build expert rubric context for repo adoption quality gates: "
        f"{project_kind} complexity simplification anti-slop product quality architecture "
        "test value dead code security secrets dependency risk truth docs CI local proof."
    )
    if tmcp_compiler is None:
        return {
            "schema": TMCP_EXPERT_ENRICHMENT_SCHEMA,
            "run_id": run_id,
            "status": "not_requested",
            "fallback": "aios_standard_rubric",
            "sufficiency_threshold": {
                "minimum_score": 6,
                "minimum_source_skill_count": 1,
                "warnings_allowed": False,
            },
            "sufficiency": {
                "score": 0,
                "source_skill_count": 0,
                "source_hash_count": 0,
                "matched_terms": [],
                "best_source_score": 0,
                "warnings": ["tmcp compiler was not provided"],
                "selected_nodes": [],
                "source_skill_nodes": [],
                "behavior_atoms": [],
            },
            "packet_summary": {
                "schema": None,
                "status": "not_requested",
                "task_id": None,
                "phase": "review",
                "domain": "repo_quality_certifier",
                "source_graph_version": None,
            },
            "selected_nodes": [],
            "influence": [],
        }
    library = skills_library_path or default_skills_library
    packet = tmcp_compiler(
        objective=objective,
        project_path=repo_path or None,
        skills_library_path=library,
        phase="review",
        domain=tmcp_domain,
    )
    source_profile = _tmcp_source_score(packet, _tmcp_relevant_terms(gate_matrix))
    sufficient = (
        packet.get("status") == "compiled"
        and source_profile["source_skill_count"] >= 1
        and source_profile["score"] >= 6
        and not source_profile["warnings"]
    )
    status = "enriched" if sufficient else "insufficient_source"
    fallback = None if sufficient else "aios_standard_rubric"
    return {
        "schema": TMCP_EXPERT_ENRICHMENT_SCHEMA,
        "run_id": run_id,
        "status": status,
        "fallback": fallback,
        "sufficiency_threshold": {
            "minimum_score": 6,
            "minimum_source_skill_count": 1,
            "warnings_allowed": False,
        },
        "sufficiency": source_profile,
        "packet_summary": {
            "schema": packet.get("schema"),
            "status": packet.get("status"),
            "task_id": packet.get("task_id"),
            "phase": packet.get("phase"),
            "domain": packet.get("domain"),
            "source_graph_version": packet.get("source_graph_version"),
            "traversal_fingerprint": packet.get("traversal_fingerprint"),
            "selected_nodes": packet.get("selected_nodes", []),
            "source_skill_nodes": packet.get("source_skill_nodes", []),
            "behavior_atoms": packet.get("behavior_atoms", []),
            "token_estimates": packet.get("token_estimates", {}),
        },
        "provenance": {
            "skills_library_path": str(library),
            "project_path": repo_path,
            "objective": objective,
        },
        "policy": (
            "TMCP expert context may enrich repo adoption rubrics only when source sufficiency "
            "passes. Otherwise the adoption workflow records an explicit AIOS-standard-rubric "
            "fallback and must not claim TMCP expertise."
        ),
    }


def build_rubric_pack(
    *,
    scan: dict[str, Any],
    gate_matrix: dict[str, Any],
    run_id: str,
    tmcp_enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repo_path = str(gate_matrix.get("repo_path") or scan.get("repo_path") or "")
    project_kind = str(gate_matrix.get("project_kind") or scan.get("project_kind") or "unknown")
    quality_profile = gate_matrix.get("quality_profile")
    quality_profile = quality_profile if isinstance(quality_profile, dict) else {}
    required_profile_gates = {
        str(item) for item in quality_profile.get("required_gates", []) if isinstance(item, str)
    }
    gate_commands = quality_profile.get("gate_commands")
    gate_commands = gate_commands if isinstance(gate_commands, dict) else {}
    classification = gate_matrix.get("classification")
    classification = classification if isinstance(classification, dict) else {}
    visual_route = gate_matrix.get("visual_proof_route")
    visual_route = visual_route if isinstance(visual_route, dict) else {}
    broad_rubrics: list[dict[str, Any]] = []
    for rubric_id in BROAD_RUBRIC_IDS:
        definition = BROAD_RUBRIC_DEFINITIONS[rubric_id]
        known_evidence = _broad_known_evidence(
            rubric_id,
            scan=scan,
            gate_matrix=gate_matrix,
        )
        broad_rubrics.append(
            {
                "id": rubric_id,
                "title": definition["title"],
                "rubric_type": "broad_quality_standard",
                "repo_class_scope": project_kind,
                "classification": classification,
                "quality_profile": quality_profile,
                "visual_proof_route": visual_route
                if rubric_id == "ui_visual_runtime_verification"
                else {},
                "quality_standard": definition["standard"],
                "command_gate_caveat": definition["gate_caveat"],
                "required_evidence": definition["required_evidence"],
                "known_evidence": known_evidence,
                "missing_evidence": _broad_missing_proof(rubric_id, known_evidence),
                "blockers": _broad_blockers(known_evidence),
                "root_causes": _broad_root_causes(rubric_id, known_evidence, definition),
                "affected_files_or_scripts": known_evidence,
                "audit_doc_path": _rubric_detail_path(run_id, rubric_id, "audit", "md"),
                "audit_json_path": _rubric_detail_path(run_id, rubric_id, "audit", "json"),
                "implementation_doc_path": _rubric_detail_path(
                    run_id,
                    rubric_id,
                    "implementation",
                    "md",
                ),
                "implementation_json_path": _rubric_detail_path(
                    run_id,
                    rubric_id,
                    "implementation",
                    "json",
                ),
                "one_hundred_percent_definition": (
                    "All required evidence is current, blockers are either fixed or explicitly "
                    "accepted, and the final adoption report can cite this rubric without relying "
                    "only on a passing command."
                ),
                "tmcp_expert_status": (tmcp_enrichment or {}).get("status", "not_requested"),
            }
        )

    raw_gates = gate_matrix.get("gates")
    gates = (
        [gate for gate in raw_gates if isinstance(gate, dict)]
        if isinstance(raw_gates, list)
        else []
    )
    gate_specific_rubrics: list[dict[str, Any]] = []
    for gate in gates:
        gate_id = str(gate.get("id", ""))
        label = str(gate.get("label", gate_id))
        profile_command = gate.get("quality_profile_command")
        profile_command = profile_command if isinstance(profile_command, dict) else {}
        known_evidence = [str(item) for item in gate.get("evidence", [])]
        if str(gate.get("status", "")) == "skipped":
            skip_reason = str(gate.get("skip_reason", "")).strip()
            known_evidence = [
                f"adoption-skip:{gate_id}:{skip_reason or 'accepted skip for repo class'}"
            ]
        gate_specific_rubrics.append(
            {
                "id": f"gate_{gate_id}",
                "title": f"{label} Gate Rubric",
                "rubric_type": "gate_specific",
                "source_gate_id": gate_id,
                "phase_cluster": _gate_phase_cluster(gate_id),
                "current_status": str(gate.get("status", "unknown")),
                "current_enforcement": str(gate.get("enforcement", "unknown")),
                "current_maturity": str(gate.get("maturity", "unknown")),
                "known_evidence": known_evidence
                or [f"repo-scan:{gate_id}:no local gate evidence found"],
                "command_gate_caveat": (
                    "A gate-specific adoption row is not proof by itself; final certification "
                    "needs a real command result or an explicit accepted exception."
                ),
                "missing_evidence": _gate_missing_proof(gate, known_evidence),
                "root_causes": _gate_root_causes(gate, known_evidence),
                "affected_files_or_scripts": _gate_affected_files_or_scripts(
                    gate,
                    known_evidence,
                ),
                "setup_actions": _gate_setup_actions(gate),
                "accepted_exceptions": _gate_accepted_exceptions(gate),
                "skip_reason": str(gate.get("skip_reason", "")),
                "quality_profile_required": bool(gate.get("quality_profile_required"))
                or any(
                    profile_gate_id in required_profile_gates
                    for profile_gate_id in _gate_profile_keys(gate_id)
                ),
                "quality_profile_command": profile_command
                or next(
                    (
                        gate_commands[profile_gate_id]
                        for profile_gate_id in _gate_profile_keys(gate_id)
                        if profile_gate_id in gate_commands
                    ),
                    {},
                ),
                "required_evidence": [
                    "latest configured command result or explicit no-command blocker",
                    "root cause and affected files/scripts",
                    "validation command for the phase",
                    "accepted exception, if any",
                ],
                "audit_doc_path": _rubric_detail_path(run_id, f"gate-{gate_id}", "audit", "md"),
                "audit_json_path": _rubric_detail_path(
                    run_id,
                    f"gate-{gate_id}",
                    "audit",
                    "json",
                ),
                "implementation_doc_path": _rubric_detail_path(
                    run_id,
                    f"gate-{gate_id}",
                    "implementation",
                    "md",
                ),
                "implementation_json_path": _rubric_detail_path(
                    run_id,
                    f"gate-{gate_id}",
                    "implementation",
                    "json",
                ),
                "one_hundred_percent_definition": (
                    "The gate has a real, non-placeholder command or approved exception; the "
                    "command passes or the exception is accepted; and adoption evidence cites the "
                    "broad rubrics that apply to this gate."
                ),
                "tmcp_expert_status": (tmcp_enrichment or {}).get("status", "not_requested"),
            }
        )

    return {
        "schema": RUBRIC_PACK_SCHEMA,
        "run_id": run_id,
        "repo_path": repo_path,
        "project_kind": project_kind,
        "classification": classification,
        "quality_profile": quality_profile,
        "visual_proof_route": visual_route,
        "procedure": [
            "Collect configured adoption-gate evidence before remediation.",
            "Audit broad repo-class quality standards independently of command pass/fail status.",
            "Audit each configured gate with a gate-specific rubric.",
            "Produce implementation docs for each rubric before execution.",
            "Create GSD phases per gate, gate cluster, or cross-cutting broad-standard finding.",
            "Rerun all gates and certification stages before claiming final adoption readiness.",
        ],
        "broad_rubrics": broad_rubrics,
        "gate_specific_rubrics": gate_specific_rubrics,
        "tmcp_expert_enrichment": tmcp_enrichment
        or {
            "schema": TMCP_EXPERT_ENRICHMENT_SCHEMA,
            "status": "not_requested",
            "fallback": "aios_standard_rubric",
        },
        "phase_planning_rule": (
            "Gate-cluster phases must be scoped from the combined broad-rubric and "
            "gate-specific audit pack, not only from the failed command list."
        ),
    }


def _adoption_action(gate_id: str, status: str, enforcement: str) -> str:
    if status == "skipped":
        return (
            f"Keep {GATE_LABELS[gate_id].lower()} as an explicit accepted skip for this repo class."
        )
    if status == "absent":
        return f"Add a repo-local {GATE_LABELS[gate_id].lower()} baseline before enforcement."
    if status == "partial":
        return f"Convert detected {GATE_LABELS[gate_id].lower()} evidence into an explicit command."
    if enforcement == "not_enforced":
        return f"Add {gate_id} to the AIOS contract or CI after a passing baseline run."
    return "Keep enforced and refresh evidence during adoption closeout."


def _phase_id_for_gate(gate_id: str) -> str:
    return "repo-local-gate-" + gate_id.replace("_", "-")


def _rubric_detail_documents_for_gate(
    rubric_detail_documents: list[dict[str, Any]],
    gate_id: str,
) -> list[dict[str, Any]]:
    gate_rubric_id = f"gate_{gate_id}"
    selected = [
        row
        for row in rubric_detail_documents
        if row.get("rubric_id") == gate_rubric_id
        or row.get("rubric_type") == "broad_quality_standard"
    ]
    return selected or rubric_detail_documents


def _phase_actions_for_gate(gate: dict[str, Any]) -> list[str]:
    gate_id = str(gate.get("id", "unknown"))
    actions = [
        str(
            gate.get("adoption_action")
            or _adoption_action(
                gate_id,
                str(gate.get("status", "unknown")),
                str(gate.get("enforcement", "unknown")),
            )
        )
    ]
    setup_actions = gate.get("setup_actions")
    if isinstance(setup_actions, list):
        actions.extend(str(action) for action in setup_actions if str(action).strip())
    actions.append(
        "Write the remediation phase in the target repo and cite the generated rubric audit and implementation docs."
    )
    if gate_id in STRICT_CLEARANCE_GATE_IDS:
        actions.extend(
            [
                f"Clear the full repo `{gate_id}` command, including inherited baseline failures outside the touched diff.",
                "Do not downgrade full-suite failures to accepted exceptions unless the exception has owner approval, expiry, affected files, and a follow-up phase; such exceptions keep final status below adoption_ready.",
            ]
        )
    return [action for action in dict.fromkeys(actions) if action]


def _phase_for_gate(
    *,
    gate: dict[str, Any],
    repo_path: str,
    rubric_detail_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    gate_id = str(gate.get("id", "unknown"))
    gate_label = str(gate.get("label") or GATE_LABELS.get(gate_id, gate_id))
    status = str(gate.get("status", "unknown"))
    enforcement = str(gate.get("enforcement", "unknown"))
    maturity = str(gate.get("maturity", "unknown"))
    skipped = status == "skipped"
    phase_type = "accepted_skip_record" if skipped else "gate_specific_remediation"
    verification = [
        f"Run the repo-local `{gate_id}` gate command or record an explicit accepted exception.",
        "Rerun AIOS repo gate adoption for this target repo and attach the fresh evidence.",
        "Do not claim quality-standard compliance unless this gate's audit and implementation docs are cited in final certification.",
    ]
    if skipped:
        verification = [
            f"Confirm `{gate_id}` is still skipped by repo classification, not by convenience.",
            "Carry the accepted skip into final adoption certification evidence.",
        ]
    return {
        "id": _phase_id_for_gate(gate_id),
        "title": f"{gate_label} repo-local phase",
        "phase_type": phase_type,
        "phase_location": "target_repo",
        "repo_path": repo_path,
        "source_gate_ids": [gate_id],
        "gate_ids": [gate_id],
        "gate_status": status,
        "gate_enforcement": enforcement,
        "gate_maturity": maturity,
        "phase_cluster": _gate_phase_cluster(gate_id),
        "cluster_rationale": "",
        "strict_clearance_required": gate_id in STRICT_CLEARANCE_GATE_IDS,
        "rubric_detail_documents": _rubric_detail_documents_for_gate(
            rubric_detail_documents,
            gate_id,
        ),
        "actions": _phase_actions_for_gate(gate),
        "verification": verification,
        "acceptance_criteria": [
            "The target repo contains the scoped phase plan or accepted skip record.",
            "The phase cites current gate evidence, broad-standard rubric evidence, and gate-specific rubric evidence.",
            "The final certification can classify adoption without mixing AIOS wiring with quality compliance.",
            "For lint and tests, the full command passes; inherited baseline failures are not treated as normal accepted exceptions.",
        ],
        "blocked_by": [f"`{gate_id}` has no real command/result evidence yet."]
        if status in {"absent", "partial"} and not skipped
        else [],
    }


def _final_certification_phase(repo_path: str) -> dict[str, Any]:
    return {
        "id": "repo-local-final-adoption-certification",
        "title": "Final repo adoption certification",
        "phase_type": "final_certification",
        "phase_location": "target_repo",
        "repo_path": repo_path,
        "source_gate_ids": [],
        "gate_ids": [],
        "phase_cluster": "adoption_certification",
        "cluster_rationale": "",
        "rubric_detail_documents": [],
        "actions": [
            "Rerun all configured adoption gates after repo-local phases complete.",
            "Confirm full lint and full test commands pass before adoption_ready certification.",
            "Classify AIOS wiring, quality-standard compliance, and release readiness separately.",
            "Record final status as adoption_ready, adopted_but_blocked, or not_adopted with blockers and accepted exceptions.",
        ],
        "verification": [
            "Final adoption output distinguishes aios_wired, quality_standard_compliant, and release_ready or stronger readiness.",
            "Inherited lint/test baselines are either cleared or represented as blocking remediation phases, not excused as completed adoption work.",
            "Every blocker and accepted exception is explicit.",
            "PROJECT_TRUTH reflects the real current state.",
        ],
        "acceptance_criteria": [
            "No full standards-compliance claim is made without the applicable gate profile, checked gate evidence, and cited rubric proof.",
            "No repo is adoption_ready while full lint or full tests fail from an inherited baseline.",
            "The target repo owns implementation phases; AIOS only coordinates evidence and certification.",
        ],
        "blocked_by": [],
    }


def build_gate_rollout_plan(
    *,
    gate_matrix: dict[str, Any],
    run_id: str,
    rubric_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gates = gate_matrix.get("gates")
    gate_rows = (
        [gate for gate in gates if isinstance(gate, dict)] if isinstance(gates, list) else []
    )
    repo_path = str(gate_matrix.get("repo_path", ""))
    rubric_detail_documents: list[dict[str, Any]] = []
    if rubric_pack:
        rubric_detail_documents = [
            {
                "rubric_id": str(rubric.get("id", "")),
                "rubric_type": str(rubric.get("rubric_type", "")),
                "audit_doc_path": str(rubric.get("audit_doc_path", "")),
                "audit_json_path": str(rubric.get("audit_json_path", "")),
                "implementation_doc_path": str(rubric.get("implementation_doc_path", "")),
                "implementation_json_path": str(rubric.get("implementation_json_path", "")),
                "phase_cluster": str(rubric.get("phase_cluster", "foundational_broad_standard")),
            }
            for rubric in _rubric_rows(rubric_pack)
        ]
    phases = [
        _phase_for_gate(
            gate=gate,
            repo_path=repo_path,
            rubric_detail_documents=rubric_detail_documents,
        )
        for gate in gate_rows
    ]
    phases.append(_final_certification_phase(repo_path))
    return {
        "schema": GATE_ROLLOUT_PLAN_SCHEMA,
        "run_id": run_id,
        "repo_path": repo_path,
        "phase_scope_policy": "repo_local_gate_scoped",
        "phase_owner": "target_repo",
        "aios_role": "portfolio_coordinator_and_evidence_ledger",
        "default_granularity": "one_phase_per_gate",
        "cluster_policy": {
            "allowed": True,
            "default": "do_not_cluster",
            "required_rationale": (
                "Only cluster gates when the generated rubric audits identify the same root "
                "cause, affected files/scripts, validation commands, and execution risk."
            ),
            "forbidden_reason": (
                "Do not cluster gates only because the repo is small, the operator wants fewer "
                "phases, or the command failures look superficially similar."
            ),
        },
        "phases": phases,
        "repo_local_phases": phases,
        "deferred_scope": [
            "Implementation is intentionally deferred to repo-local phases owned by the target repo."
        ],
        "rubric_pack_schema": rubric_pack.get("schema") if rubric_pack else None,
        "rubric_detail_documents": rubric_detail_documents,
    }


def validate_repo_scan(scan: dict[str, Any]) -> ValidationResult:
    issues: list[str] = []
    if scan.get("schema") != REPO_SCAN_SCHEMA:
        issues.append("Repo scan schema is invalid")
    if not scan.get("repo_path"):
        issues.append("Repo scan is missing repo_path")
    if not isinstance(scan.get("gate_evidence"), dict):
        issues.append("Repo scan is missing gate_evidence")
    return {"validation_key": "repo_gate_scan_has_evidence", "passed": not issues, "issues": issues}


def validate_gate_matrix(matrix: dict[str, Any]) -> ValidationResult:
    issues: list[str] = []
    if matrix.get("schema") != GATE_MATRIX_SCHEMA:
        issues.append("Gate matrix schema is invalid")
    gates = matrix.get("gates")
    gate_ids: set[str] = set()
    if isinstance(gates, list):
        gate_ids = {str(gate.get("id")) for gate in gates if isinstance(gate, dict)}
    core_gate_ids: set[str] = set(CORE_GATE_IDS)
    missing = sorted(core_gate_ids - gate_ids)
    if missing:
        issues.append("Gate matrix missing core gates: " + ", ".join(missing))
    return {"validation_key": "gate_matrix_has_core_gates", "passed": not issues, "issues": issues}


def validate_rubric_pack(pack: dict[str, Any]) -> ValidationResult:
    issues: list[str] = []
    if pack.get("schema") != RUBRIC_PACK_SCHEMA:
        issues.append("Rubric pack schema is invalid")
    broad = pack.get("broad_rubrics")
    if not isinstance(broad, list) or not broad:
        issues.append("Rubric pack is missing broad rubrics")
    else:
        broad_ids = {str(item.get("id")) for item in broad if isinstance(item, dict)}
        broad_rubric_ids: set[str] = set(BROAD_RUBRIC_IDS)
        missing_broad = sorted(broad_rubric_ids - broad_ids)
        if missing_broad:
            issues.append("Rubric pack missing broad rubrics: " + ", ".join(missing_broad))
    gate_specific = pack.get("gate_specific_rubrics")
    if not isinstance(gate_specific, list) or not gate_specific:
        issues.append("Rubric pack is missing gate-specific rubrics")
    enrichment = pack.get("tmcp_expert_enrichment")
    if not isinstance(enrichment, dict):
        issues.append("Rubric pack is missing TMCP expert enrichment status")
    return {
        "validation_key": "rubric_pack_has_broad_and_gate_rubrics",
        "passed": not issues,
        "issues": issues,
    }


def validate_tmcp_expert_enrichment(enrichment: dict[str, Any]) -> ValidationResult:
    issues: list[str] = []
    if enrichment.get("schema") != TMCP_EXPERT_ENRICHMENT_SCHEMA:
        issues.append("TMCP expert enrichment schema is invalid")
    status = enrichment.get("status")
    if status not in {"enriched", "insufficient_source", "not_requested"}:
        issues.append("TMCP expert enrichment status is invalid")
    if status == "enriched" and not enrichment.get("packet_summary"):
        issues.append("TMCP expert enrichment is missing packet summary")
    if status == "insufficient_source" and enrichment.get("fallback") != "aios_standard_rubric":
        issues.append("Insufficient TMCP source must fall back to AIOS standard rubric")
    return {
        "validation_key": "tmcp_expert_enrichment_has_sufficiency_status",
        "passed": not issues,
        "issues": issues,
    }


def validate_gate_rollout_plan(plan: dict[str, Any]) -> ValidationResult:
    issues: list[str] = []
    if plan.get("schema") != GATE_ROLLOUT_PLAN_SCHEMA:
        issues.append("Gate rollout plan schema is invalid")
    if plan.get("phase_scope_policy") != "repo_local_gate_scoped":
        issues.append("Gate rollout plan must use repo_local_gate_scoped phase scope")
    if plan.get("phase_owner") != "target_repo":
        issues.append("Gate rollout plan phases must be owned by the target repo")
    if plan.get("aios_role") != "portfolio_coordinator_and_evidence_ledger":
        issues.append("Gate rollout plan must keep AIOS as coordinator and evidence ledger")
    phases = plan.get("phases")
    if not isinstance(phases, list) or not phases:
        issues.append("Gate rollout plan has no phases")
    else:
        has_final_certification = False
        for phase in phases:
            if not isinstance(phase, dict):
                issues.append("Gate rollout phase is invalid")
                continue
            if phase.get("phase_location") != "target_repo":
                issues.append(f"{phase.get('id', 'phase')} is not scoped to the target repo")
            source_gate_ids = phase.get("source_gate_ids")
            if not isinstance(source_gate_ids, list):
                issues.append(f"{phase.get('id', 'phase')} is missing source_gate_ids")
                source_gate_ids = []
            if len(source_gate_ids) > 1 and not str(phase.get("cluster_rationale", "")).strip():
                issues.append(
                    f"{phase.get('id', 'phase')} clusters gates without an explicit rationale"
                )
            if phase.get("phase_type") == "final_certification":
                has_final_certification = True
            verification = phase.get("verification")
            if not isinstance(verification, list) or not verification:
                issues.append(f"{phase.get('id', 'phase')} is missing verification")
        if not has_final_certification:
            issues.append("Gate rollout plan is missing a final certification phase")
    return {
        "validation_key": "gate_rollout_has_repo_local_gate_phases",
        "passed": not issues,
        "issues": issues,
    }


def render_gate_matrix_markdown(matrix: dict[str, Any]) -> str:
    lines = [
        f"# Repo Gate Matrix: {matrix.get('run_id', '')}",
        "",
        f"Repo: `{matrix.get('repo_path', '')}`",
        f"Project kind: `{matrix.get('project_kind', 'unknown')}`",
        "",
        "| Gate | Status | Enforcement | Maturity | Evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for gate in matrix.get("gates", []):
        if not isinstance(gate, dict):
            continue
        evidence = ", ".join(str(item) for item in gate.get("evidence", [])) or "none"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(gate.get("label", "")),
                    str(gate.get("status", "")),
                    str(gate.get("enforcement", "")),
                    str(gate.get("maturity", "")),
                    evidence,
                ]
            )
            + " |"
        )
    return "\n".join(lines).rstrip() + "\n"


def render_rubric_pack_markdown(pack: dict[str, Any]) -> str:
    enrichment = pack.get("tmcp_expert_enrichment")
    tmcp_status = (
        str(enrichment.get("status", "unknown")) if isinstance(enrichment, dict) else "unknown"
    )
    tmcp_fallback = (
        str(enrichment.get("fallback", "none")) if isinstance(enrichment, dict) else "unknown"
    )
    lines = [
        f"# Repo Quality Rubric Pack: {pack.get('run_id', '')}",
        "",
        f"Repo: `{pack.get('repo_path', '')}`",
        f"Project kind: `{pack.get('project_kind', 'unknown')}`",
        f"TMCP expert status: `{tmcp_status}`",
        f"TMCP fallback: `{tmcp_fallback}`",
        "",
        "## Procedure",
        "",
    ]
    for step in pack.get("procedure", []):
        lines.append(f"- {step}")
    lines.extend(
        [
            "",
            "## Broad Quality Rubrics",
            "",
            "| Rubric | Command Gate Caveat | Required Evidence |",
            "| --- | --- | --- |",
        ]
    )
    for rubric in pack.get("broad_rubrics", []):
        if not isinstance(rubric, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(rubric.get("title", "")),
                    str(rubric.get("command_gate_caveat", "")),
                    "; ".join(str(item) for item in rubric.get("required_evidence", [])),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Gate-Specific Rubrics",
            "",
            "| Gate | Status | Enforcement | Phase Cluster | Required Evidence |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for rubric in pack.get("gate_specific_rubrics", []):
        if not isinstance(rubric, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(rubric.get("source_gate_id", "")),
                    str(rubric.get("current_status", "")),
                    str(rubric.get("current_enforcement", "")),
                    str(rubric.get("phase_cluster", "")),
                    "; ".join(str(item) for item in rubric.get("required_evidence", [])),
                ]
            )
            + " |"
        )
    lines.extend(["", f"Planning rule: {pack.get('phase_planning_rule', '')}"])
    return "\n".join(lines).rstrip() + "\n"


def render_tmcp_expert_enrichment_markdown(enrichment: dict[str, Any]) -> str:
    sufficiency = enrichment.get("sufficiency")
    sufficiency = sufficiency if isinstance(sufficiency, dict) else {}
    packet_summary = enrichment.get("packet_summary")
    packet_summary = packet_summary if isinstance(packet_summary, dict) else {}
    lines = [
        f"# TMCP Expert Enrichment: {enrichment.get('run_id', '')}",
        "",
        f"Status: `{enrichment.get('status', 'unknown')}`",
        f"Fallback: `{enrichment.get('fallback', 'none')}`",
        f"Sufficiency score: `{sufficiency.get('score', 0)}`",
        f"Source skill count: `{sufficiency.get('source_skill_count', 0)}`",
        f"Best source score: `{sufficiency.get('best_source_score', 0)}`",
        "",
        "## Selected Nodes",
        "",
    ]
    for node in packet_summary.get("selected_nodes", []):
        lines.append(f"- `{node}`")
    lines.extend(["", "## Matched Terms", ""])
    for term in sufficiency.get("matched_terms", []):
        lines.append(f"- `{term}`")
    lines.extend(["", "## Policy", "", str(enrichment.get("policy", ""))])
    return "\n".join(lines).rstrip() + "\n"


def _as_string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _as_dict_list(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _rubric_rows(pack: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("broad_rubrics", "gate_specific_rubrics"):
        value = pack.get(key)
        if isinstance(value, list):
            rows.extend(item for item in value if isinstance(item, dict))
    return rows


def _rubric_validation_commands(rubric: dict[str, Any]) -> list[str]:
    source_gate_id = str(rubric.get("source_gate_id", "")).strip()
    if str(rubric.get("current_status", "")).strip() == "skipped":
        return [
            f"Confirm the accepted `{source_gate_id}` skip still applies to this repo class.",
            "Record the skip reason in final adoption certification instead of running a fake/no-op command.",
        ]
    if source_gate_id in STRICT_CLEARANCE_GATE_IDS:
        return [
            f"Run the full repo `{source_gate_id}` command, not only touched-file or focused checks.",
            "Treat inherited baseline failures as remediation targets and keep the repo blocked until the full command passes.",
            "If a temporary exception is unavoidable, record owner, expiry, affected files, and the exact follow-up phase; do not classify the repo as adoption_ready.",
        ]
    if source_gate_id:
        return [
            f"Run the configured `{source_gate_id}` gate through AIOS linked-repo quality evidence.",
            "Record a passing command result or an explicit accepted exception before certification.",
        ]
    return [
        "Complete this broad-standard audit with repo-specific evidence.",
        "Cite this audit from the final adoption certification before claiming compliance.",
    ]


def _rubric_blockers(rubric: dict[str, Any]) -> list[str]:
    blockers = _as_string_list(rubric.get("blockers"))
    known_evidence = _as_string_list(rubric.get("known_evidence"))
    current_status = str(rubric.get("current_status", "")).strip()
    current_enforcement = str(rubric.get("current_enforcement", "")).strip()
    if current_status and current_status not in {"present", "skipped"}:
        blockers.append(f"Gate status is `{current_status}`, not `present`.")
    if current_enforcement and current_enforcement not in {"hard", "soft", "accepted_exception"}:
        blockers.append(f"Gate enforcement is `{current_enforcement}`, not enforced.")
    if not known_evidence:
        blockers.append("Repo-specific evidence has not been filled into this rubric yet.")
    return blockers


def build_rubric_audit_document(rubric: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    required_evidence = _as_string_list(rubric.get("required_evidence"))
    known_evidence = _as_string_list(rubric.get("known_evidence"))
    blockers = _rubric_blockers(rubric)
    missing_evidence = _as_string_list(rubric.get("missing_evidence"))
    if not missing_evidence:
        missing_evidence = [item for item in required_evidence if item not in known_evidence]
    accepted_exceptions = _as_string_list(rubric.get("accepted_exceptions"))
    if not accepted_exceptions:
        accepted_exceptions = [
            "No accepted exceptions were generated; any exception must be explicitly owner-approved before final certification."
        ]
    return {
        "schema": RUBRIC_AUDIT_SCHEMA,
        "run_id": pack.get("run_id", ""),
        "repo_path": pack.get("repo_path", ""),
        "project_kind": pack.get("project_kind", "unknown"),
        "classification": pack.get("classification", {}),
        "quality_profile": pack.get("quality_profile", {}),
        "visual_proof_route": rubric.get("visual_proof_route")
        or pack.get("visual_proof_route", {}),
        "rubric_id": rubric.get("id", ""),
        "rubric_type": rubric.get("rubric_type", ""),
        "title": rubric.get("title", ""),
        "quality_standard": rubric.get("quality_standard", rubric.get("title", "")),
        "command_gate_caveat": rubric.get("command_gate_caveat", ""),
        "source_gate_id": rubric.get("source_gate_id"),
        "phase_cluster": rubric.get("phase_cluster", "foundational_broad_standard"),
        "required_evidence": required_evidence,
        "known_evidence": known_evidence,
        "current_status": rubric.get("current_status"),
        "current_enforcement": rubric.get("current_enforcement"),
        "current_maturity": rubric.get("current_maturity"),
        "quality_profile_required": rubric.get("quality_profile_required"),
        "quality_profile_command": rubric.get("quality_profile_command", {}),
        "missing_evidence": missing_evidence,
        "blockers": blockers,
        "accepted_exceptions": accepted_exceptions,
        "validation_commands": _rubric_validation_commands(rubric),
        "tmcp_expert_status": rubric.get("tmcp_expert_status", "not_requested"),
        "one_hundred_percent_definition": rubric.get("one_hundred_percent_definition", ""),
    }


def build_rubric_implementation_document(
    rubric: dict[str, Any],
    pack: dict[str, Any],
) -> dict[str, Any]:
    audit = build_rubric_audit_document(rubric, pack)
    phase_cluster = str(audit.get("phase_cluster") or "foundational_broad_standard")
    known_evidence = _as_string_list(audit.get("known_evidence"))
    visual_route = audit.get("visual_proof_route")
    visual_route = visual_route if isinstance(visual_route, dict) else {}
    visual_steps = _as_string_list(visual_route.get("recommended_evidence"))
    recommended_phase_type = (
        "gate_specific_phase"
        if rubric.get("rubric_type") == "gate_specific"
        else "foundational_or_cross_cutting_phase"
    )
    implementation_steps = [
        "Collect or refresh the required evidence listed in the audit document.",
        "Fix blockers or record accepted exceptions with owner and validation proof.",
        "Rerun the validation commands and update the adoption report.",
    ]
    source_gate_id = str(rubric.get("source_gate_id", "")).strip()
    if source_gate_id in STRICT_CLEARANCE_GATE_IDS:
        implementation_steps = [
            f"Run the full repo `{source_gate_id}` command and capture the complete failure list.",
            "Group inherited failures by root cause and create remediation slices until the full command passes.",
            "Use focused checks only as interim debugging proof; they are not adoption certification proof.",
            "If a temporary exception is unavoidable, record owner, expiry, affected files, validation command, and follow-up phase; keep final status below adoption_ready.",
        ]
    setup_actions = _as_string_list(rubric.get("setup_actions"))
    if setup_actions:
        implementation_steps = [
            *setup_actions,
            *implementation_steps,
        ]
    if rubric.get("id") == "ui_visual_runtime_verification":
        implementation_steps = [
            *setup_actions,
            "Collect or refresh the required evidence listed in the audit document.",
            *visual_steps,
            "Fix blockers or record accepted exceptions with owner and validation proof.",
            "Rerun the validation commands and update the adoption report.",
        ]
    root_causes = _as_string_list(rubric.get("root_causes")) or [
        f"{audit.get('title', 'This rubric')} still needs fresh pass/fail evidence attached before certification."
    ]
    affected_files_or_scripts = _as_string_list(rubric.get("affected_files_or_scripts"))
    if not affected_files_or_scripts:
        affected_files_or_scripts = known_evidence or [
            f"repo-scan:{audit.get('rubric_id', 'rubric')}:no affected files inferred"
        ]
    return {
        "schema": RUBRIC_IMPLEMENTATION_SCHEMA,
        "run_id": pack.get("run_id", ""),
        "repo_path": pack.get("repo_path", ""),
        "project_kind": pack.get("project_kind", "unknown"),
        "classification": pack.get("classification", {}),
        "quality_profile": pack.get("quality_profile", {}),
        "visual_proof_route": visual_route,
        "rubric_id": rubric.get("id", ""),
        "rubric_type": rubric.get("rubric_type", ""),
        "title": rubric.get("title", ""),
        "phase_cluster": phase_cluster,
        "recommended_phase_type": recommended_phase_type,
        "root_causes": root_causes,
        "affected_files_or_scripts": affected_files_or_scripts,
        "implementation_steps": implementation_steps,
        "validation_commands": _as_string_list(audit.get("validation_commands")),
        "execution_risks": [
            "Do not weaken the configured gate to make adoption pass.",
            "Do not claim broad standards compliance from a narrow command pass.",
        ],
        "accepted_exceptions": _as_string_list(audit.get("accepted_exceptions")),
        "ready_for_gsd_phase": True,
        "audit_doc_path": rubric.get("audit_doc_path"),
        "audit_json_path": rubric.get("audit_json_path"),
    }


def _markdown_list(items: list[str], *, empty_message: str) -> list[str]:
    return [f"- {item}" for item in items] if items else [f"- {empty_message}"]


def render_rubric_audit_markdown(document: dict[str, Any]) -> str:
    lines = [
        f"# Rubric Audit: {document.get('title', '')}",
        "",
        f"Rubric ID: `{document.get('rubric_id', '')}`",
        f"Rubric type: `{document.get('rubric_type', '')}`",
        f"TMCP expert status: `{document.get('tmcp_expert_status', 'not_requested')}`",
        "",
        "## Standard Being Judged",
        "",
        str(document.get("quality_standard", "")),
        "",
        "## Why Command Pass/Fail Is Not Enough",
        "",
        str(document.get("command_gate_caveat", "")),
        "",
        "## Required Evidence",
        "",
        *_markdown_list(
            _as_string_list(document.get("required_evidence")),
            empty_message="No required evidence categories were generated for this rubric.",
        ),
        "",
        "## Current Evidence Found",
        "",
        *_markdown_list(
            _as_string_list(document.get("known_evidence")),
            empty_message="No scan-derived evidence was found for this rubric.",
        ),
        "",
        "## Blockers",
        "",
        *_markdown_list(
            _as_string_list(document.get("blockers")),
            empty_message="No generated blockers; final certification still requires fresh proof.",
        ),
        "",
        "## Missing Proof",
        "",
        *_markdown_list(
            _as_string_list(document.get("missing_evidence")),
            empty_message="No missing proof detected by the generated scan.",
        ),
        "",
        "## Accepted Exceptions",
        "",
        *_markdown_list(
            _as_string_list(document.get("accepted_exceptions")),
            empty_message="No accepted exceptions were generated.",
        ),
        "",
        "## Validation Commands",
        "",
        *_markdown_list(
            _as_string_list(document.get("validation_commands")),
            empty_message="No validation commands were generated.",
        ),
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_rubric_implementation_markdown(document: dict[str, Any]) -> str:
    lines = [
        f"# Rubric Implementation Plan: {document.get('title', '')}",
        "",
        f"Rubric ID: `{document.get('rubric_id', '')}`",
        f"Phase cluster: `{document.get('phase_cluster', '')}`",
        f"Recommended phase type: `{document.get('recommended_phase_type', '')}`",
        f"Ready for GSD phase: `{document.get('ready_for_gsd_phase', False)}`",
        "",
        "## What Needs To Change To Reach 100%",
        "",
        *_markdown_list(
            _as_string_list(document.get("implementation_steps")),
            empty_message="No implementation steps were generated.",
        ),
        "",
        "## Root Causes",
        "",
        *_markdown_list(
            _as_string_list(document.get("root_causes")),
            empty_message="No root causes were generated.",
        ),
        "",
        "## Likely Affected Files Or Scripts",
        "",
        *_markdown_list(
            _as_string_list(document.get("affected_files_or_scripts")),
            empty_message="No affected files or scripts were inferred.",
        ),
        "",
        "## Execution Risks",
        "",
        *_markdown_list(
            _as_string_list(document.get("execution_risks")),
            empty_message="No execution risks were generated.",
        ),
        "",
        "## Verification Commands",
        "",
        *_markdown_list(
            _as_string_list(document.get("validation_commands")),
            empty_message="No verification commands were generated.",
        ),
        "",
        "## Phase Scope",
        "",
        (
            "This belongs in a gate-specific phase."
            if document.get("recommended_phase_type") == "gate_specific_phase"
            else "This belongs in a foundational or cross-cutting phase."
        ),
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_rubric_detail_documents(
    *, output_dir: Path, rubric_pack: dict[str, Any]
) -> dict[str, Any]:
    rubrics_dir = output_dir / "rubrics"
    rubrics_dir.mkdir(parents=True, exist_ok=True)
    documents: list[dict[str, Any]] = []
    for rubric in _rubric_rows(rubric_pack):
        rubric_id = str(rubric.get("id", "rubric"))
        audit_document = build_rubric_audit_document(rubric, rubric_pack)
        implementation_document = build_rubric_implementation_document(rubric, rubric_pack)
        audit_json_path = rubrics_dir / f"{rubric_id}.audit.json"
        audit_markdown_path = rubrics_dir / f"{rubric_id}.audit.md"
        implementation_json_path = rubrics_dir / f"{rubric_id}.implementation.json"
        implementation_markdown_path = rubrics_dir / f"{rubric_id}.implementation.md"
        _json_dump(audit_json_path, audit_document)
        audit_markdown_path.write_text(
            render_rubric_audit_markdown(audit_document),
            encoding="utf-8",
        )
        _json_dump(implementation_json_path, implementation_document)
        implementation_markdown_path.write_text(
            render_rubric_implementation_markdown(implementation_document),
            encoding="utf-8",
        )
        documents.append(
            {
                "rubric_id": rubric_id,
                "rubric_type": rubric.get("rubric_type", ""),
                "audit_markdown_path": str(audit_markdown_path),
                "audit_json_path": str(audit_json_path),
                "implementation_markdown_path": str(implementation_markdown_path),
                "implementation_json_path": str(implementation_json_path),
                "phase_cluster": implementation_document.get("phase_cluster"),
                "recommended_phase_type": implementation_document.get("recommended_phase_type"),
            }
        )
    return {
        "schema": RUBRIC_DETAIL_MANIFEST_SCHEMA,
        "run_id": rubric_pack.get("run_id", ""),
        "rubrics_dir": str(rubrics_dir),
        "document_count": len(documents) * 4,
        "rubric_count": len(documents),
        "documents": documents,
    }


def render_rubric_detail_manifest_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        f"# Rubric Detail Document Manifest: {manifest.get('run_id', '')}",
        "",
        f"Rubrics directory: `{manifest.get('rubrics_dir', '')}`",
        f"Rubric count: `{manifest.get('rubric_count', 0)}`",
        f"Document count: `{manifest.get('document_count', 0)}`",
        "",
        "| Rubric | Type | Phase Cluster | Audit | Implementation |",
        "| --- | --- | --- | --- | --- |",
    ]
    documents = manifest.get("documents")
    if isinstance(documents, list):
        for row in documents:
            if not isinstance(row, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("rubric_id", "")),
                        str(row.get("rubric_type", "")),
                        str(row.get("phase_cluster", "")),
                        str(row.get("audit_markdown_path", "")),
                        str(row.get("implementation_markdown_path", "")),
                    ]
                )
                + " |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _read_json_file(path: Path) -> dict[str, Any]:
    return _read_json(path)


def _required_markdown_sections(kind: str) -> tuple[str, ...]:
    if kind == "audit":
        return (
            "## Current Evidence Found",
            "## Blockers",
            "## Missing Proof",
            "## Accepted Exceptions",
            "## Validation Commands",
        )
    return (
        "## Root Causes",
        "## Likely Affected Files Or Scripts",
        "## Execution Risks",
        "## Verification Commands",
        "## Phase Scope",
    )


def _phase_planning_blockers(
    blockers: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> list[dict[str, Any]]:
    phase_blockers: list[dict[str, Any]] = []
    if blockers:
        phase_blockers.append(
            {
                "code": "structural_doc_quality_blockers",
                "count": len(blockers),
                "message": "Artifact-level blockers must be fixed before phase planning.",
            }
        )
    warning_counts: dict[str, int] = {}
    warning_examples: dict[str, str] = {}
    for warning in warnings:
        code = str(warning.get("code", "")).strip()
        if code not in PHASE_PLANNING_BLOCKING_WARNING_CODES:
            continue
        warning_counts[code] = warning_counts.get(code, 0) + 1
        warning_examples.setdefault(code, str(warning.get("message", "")))
    for code in sorted(warning_counts):
        phase_blockers.append(
            {
                "code": code,
                "count": warning_counts[code],
                "message": PHASE_PLANNING_BLOCKING_WARNING_CODES[code],
                "example": warning_examples.get(code, ""),
            }
        )
    return phase_blockers


def evaluate_adoption_doc_quality(output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / "rubric-detail-manifest.json"
    manifest = _read_json_file(manifest_path)
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    checked_docs = 0
    if manifest.get("schema") != RUBRIC_DETAIL_MANIFEST_SCHEMA:
        blockers.append(
            {
                "code": "manifest_schema_invalid",
                "message": "rubric-detail-manifest.json is missing or has an invalid schema.",
            }
        )
    documents = manifest.get("documents")
    if not isinstance(documents, list) or not documents:
        blockers.append(
            {
                "code": "manifest_documents_missing",
                "message": "rubric detail manifest does not list any rubric documents.",
            }
        )
        documents = []
    for row in documents:
        if not isinstance(row, dict):
            continue
        rubric_id = str(row.get("rubric_id", "unknown"))
        path_pairs = (
            (
                "audit",
                Path(str(row.get("audit_markdown_path", ""))),
                Path(str(row.get("audit_json_path", ""))),
            ),
            (
                "implementation",
                Path(str(row.get("implementation_markdown_path", ""))),
                Path(str(row.get("implementation_json_path", ""))),
            ),
        )
        for kind, markdown_path, json_path in path_pairs:
            checked_docs += 1
            if not markdown_path.exists():
                blockers.append(
                    {
                        "code": f"{kind}_markdown_missing",
                        "message": f"{rubric_id} is missing {kind} Markdown doc.",
                    }
                )
                continue
            if not json_path.exists():
                blockers.append(
                    {
                        "code": f"{kind}_json_missing",
                        "message": f"{rubric_id} is missing {kind} JSON doc.",
                    }
                )
                continue
            markdown = markdown_path.read_text(encoding="utf-8", errors="replace")
            for section in _required_markdown_sections(kind):
                if section not in markdown:
                    blockers.append(
                        {
                            "code": f"{kind}_section_missing",
                            "message": f"{rubric_id} {kind} doc is missing section {section}.",
                        }
                    )
            payload = _read_json_file(json_path)
            expected_schema = (
                RUBRIC_AUDIT_SCHEMA if kind == "audit" else RUBRIC_IMPLEMENTATION_SCHEMA
            )
            if payload.get("schema") != expected_schema:
                blockers.append(
                    {
                        "code": f"{kind}_schema_invalid",
                        "message": f"{rubric_id} {kind} JSON schema is invalid.",
                    }
                )
            validation_commands = _as_string_list(payload.get("validation_commands"))
            if not validation_commands:
                blockers.append(
                    {
                        "code": f"{kind}_validation_commands_missing",
                        "message": f"{rubric_id} {kind} JSON is missing validation commands.",
                    }
                )
            if "none recorded" in markdown:
                warnings.append(
                    {
                        "code": f"{kind}_empty_section",
                        "message": f"{rubric_id} {kind} doc still has empty generated sections.",
                    }
                )
            if kind == "audit" and not _as_string_list(payload.get("known_evidence")):
                warnings.append(
                    {
                        "code": "audit_no_known_evidence",
                        "message": f"{rubric_id} audit has no repo-specific evidence yet.",
                    }
                )
            if kind == "implementation" and "fill repo-specific root cause" in " ".join(
                _as_string_list(payload.get("root_causes"))
            ):
                warnings.append(
                    {
                        "code": "implementation_generic_root_cause",
                        "message": f"{rubric_id} implementation doc still has generic root-cause text.",
                    }
                )
            if rubric_id == "ui_visual_runtime_verification" and kind == "implementation":
                visual_route = payload.get("visual_proof_route")
                visual_route = visual_route if isinstance(visual_route, dict) else {}
                if not visual_route.get("route"):
                    blockers.append(
                        {
                            "code": "ui_visual_route_missing",
                            "message": "UI visual runtime rubric is missing a recommended proof route.",
                        }
                    )
    status = "fail" if blockers else "warning" if warnings else "pass"
    phase_blockers = _phase_planning_blockers(blockers, warnings)
    structurally_valid = not blockers
    ready_for_phase_planning = structurally_valid and not phase_blockers
    return {
        "schema": ADOPTION_DOC_QUALITY_SCHEMA,
        "output_dir": str(output_dir),
        "run_id": manifest.get("run_id", ""),
        "status": status,
        "passed": not blockers,
        "structurally_valid": structurally_valid,
        "ready_for_phase_planning": ready_for_phase_planning,
        "ready_for_execution": ready_for_phase_planning and not warnings,
        "checked_document_pairs": checked_docs,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "phase_planning_blocker_count": len(phase_blockers),
        "phase_planning_blockers": phase_blockers,
        "blockers": blockers,
        "warnings": warnings,
        "manifest_path": str(manifest_path),
    }


def render_adoption_doc_quality_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Adoption Doc Quality: {report.get('run_id', '')}",
        "",
        f"Status: `{report.get('status', 'unknown')}`",
        f"Structurally valid: `{report.get('structurally_valid', False)}`",
        f"Ready for phase planning: `{report.get('ready_for_phase_planning', False)}`",
        f"Ready for execution: `{report.get('ready_for_execution', False)}`",
        f"Checked document pairs: `{report.get('checked_document_pairs', 0)}`",
        f"Blockers: `{report.get('blocker_count', 0)}`",
        f"Warnings: `{report.get('warning_count', 0)}`",
        f"Phase planning blockers: `{report.get('phase_planning_blocker_count', 0)}`",
        "",
        "## Phase Planning Blockers",
        "",
    ]
    phase_blockers = report.get("phase_planning_blockers")
    if isinstance(phase_blockers, list) and phase_blockers:
        lines.extend(
            (
                f"- `{row.get('code', 'phase_blocker')}` "
                f"({row.get('count', 1)}): {row.get('message', '')}"
            )
            for row in phase_blockers
            if isinstance(row, dict)
        )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Blockers",
            "",
        ]
    )
    blockers = report.get("blockers")
    if isinstance(blockers, list) and blockers:
        lines.extend(
            f"- `{row.get('code', 'blocker')}`: {row.get('message', '')}"
            for row in blockers
            if isinstance(row, dict)
        )
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    warnings = report.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.extend(
            f"- `{row.get('code', 'warning')}`: {row.get('message', '')}"
            for row in warnings
            if isinstance(row, dict)
        )
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def write_adoption_doc_quality_report(output_dir: Path) -> dict[str, Path]:
    report = evaluate_adoption_doc_quality(output_dir)
    json_path = output_dir / "adoption-doc-quality.json"
    markdown_path = output_dir / "adoption-doc-quality.md"
    _json_dump(json_path, report)
    markdown_path.write_text(render_adoption_doc_quality_markdown(report), encoding="utf-8")
    return {
        "adoption_doc_quality_json": json_path,
        "adoption_doc_quality_markdown": markdown_path,
    }


def render_gate_rollout_markdown(plan: dict[str, Any]) -> str:
    cluster_policy = plan.get("cluster_policy")
    cluster_policy = cluster_policy if isinstance(cluster_policy, dict) else {}
    lines = [
        f"# Repo Gate Adoption Plan: {plan.get('run_id', '')}",
        "",
        f"Repo: `{plan.get('repo_path', '')}`",
        f"Phase scope policy: `{plan.get('phase_scope_policy', '')}`",
        f"Phase owner: `{plan.get('phase_owner', '')}`",
        f"AIOS role: `{plan.get('aios_role', '')}`",
        f"Default granularity: `{plan.get('default_granularity', '')}`",
        "",
        "## Cluster Policy",
        "",
        f"- Default: `{cluster_policy.get('default', '')}`",
        f"- Required rationale: {cluster_policy.get('required_rationale', '')}",
        f"- Forbidden reason: {cluster_policy.get('forbidden_reason', '')}",
        "",
        "## Repo-Local Phases",
        "",
    ]
    for phase in plan.get("phases", []):
        if not isinstance(phase, dict):
            continue
        source_gate_ids = phase.get("source_gate_ids", [])
        source_gate_text = ", ".join(str(item) for item in source_gate_ids)
        blocked_by = phase.get("blocked_by", [])
        blocked_by_text = "; ".join(str(item) for item in blocked_by) if blocked_by else "none"
        acceptance_criteria = phase.get("acceptance_criteria", [])
        lines.extend(
            [
                f"## {phase.get('id')}: {phase.get('title')}",
                "",
                f"- Location: `{phase.get('phase_location', '')}`",
                f"- Phase type: `{phase.get('phase_type', '')}`",
                "- Source gates: " + source_gate_text,
                f"- Cluster rationale: {phase.get('cluster_rationale') or 'none'}",
                "- Actions: " + "; ".join(str(item) for item in phase.get("actions", [])),
                "- Verification: " + "; ".join(str(item) for item in phase.get("verification", [])),
                "- Acceptance criteria: " + "; ".join(str(item) for item in acceptance_criteria),
                "- Blocked by: " + blocked_by_text,
                "",
            ]
        )
        rubric_docs = phase.get("rubric_detail_documents")
        if isinstance(rubric_docs, list) and rubric_docs:
            lines.extend(["Rubric detail documents:", ""])
            for row in rubric_docs:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    "- "
                    + str(row.get("rubric_id", ""))
                    + ": audit "
                    + str(row.get("audit_doc_path", ""))
                    + "; implementation "
                    + str(row.get("implementation_doc_path", ""))
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_gate_adoption_artifacts(
    *,
    output_dir: Path,
    repo_root: Path | None = None,
    repo_scan: dict[str, Any],
    gate_matrix: dict[str, Any],
    rubric_pack: dict[str, Any],
    rollout_plan: dict[str, Any],
) -> dict[str, Path]:
    if repo_root is not None:
        ensure_aios_backfill_gitignored(repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "repo_scan_json": output_dir / "repo-scan.json",
        "gate_matrix_json": output_dir / "gate-matrix.json",
        "gate_matrix_markdown": output_dir / "gate-matrix.md",
        "tmcp_expert_enrichment_json": output_dir / "tmcp-expert-enrichment.json",
        "tmcp_expert_enrichment_markdown": output_dir / "tmcp-expert-enrichment.md",
        "rubric_pack_json": output_dir / "rubric-pack.json",
        "rubric_pack_markdown": output_dir / "rubric-pack.md",
        "rubric_docs_dir": output_dir / "rubrics",
        "rubric_detail_manifest_json": output_dir / "rubric-detail-manifest.json",
        "rubric_detail_manifest_markdown": output_dir / "rubric-detail-manifest.md",
        "rollout_plan_json": output_dir / "rollout-plan.json",
        "rollout_plan_markdown": output_dir / "rollout-plan.md",
    }
    _json_dump(paths["repo_scan_json"], repo_scan)
    _json_dump(paths["gate_matrix_json"], gate_matrix)
    paths["gate_matrix_markdown"].write_text(
        render_gate_matrix_markdown(gate_matrix),
        encoding="utf-8",
    )
    tmcp_enrichment = rubric_pack.get("tmcp_expert_enrichment")
    tmcp_enrichment = tmcp_enrichment if isinstance(tmcp_enrichment, dict) else {}
    _json_dump(paths["tmcp_expert_enrichment_json"], tmcp_enrichment)
    paths["tmcp_expert_enrichment_markdown"].write_text(
        render_tmcp_expert_enrichment_markdown(tmcp_enrichment),
        encoding="utf-8",
    )
    _json_dump(paths["rubric_pack_json"], rubric_pack)
    paths["rubric_pack_markdown"].write_text(
        render_rubric_pack_markdown(rubric_pack),
        encoding="utf-8",
    )
    rubric_detail_manifest = write_rubric_detail_documents(
        output_dir=output_dir,
        rubric_pack=rubric_pack,
    )
    _json_dump(paths["rubric_detail_manifest_json"], rubric_detail_manifest)
    paths["rubric_detail_manifest_markdown"].write_text(
        render_rubric_detail_manifest_markdown(rubric_detail_manifest),
        encoding="utf-8",
    )
    _json_dump(paths["rollout_plan_json"], rollout_plan)
    paths["rollout_plan_markdown"].write_text(
        render_gate_rollout_markdown(rollout_plan),
        encoding="utf-8",
    )
    return paths
