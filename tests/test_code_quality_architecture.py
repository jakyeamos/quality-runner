from __future__ import annotations

from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _ui_no_server_imports_config() -> dict:
    return {
        "architecture": {
            "enabled": True,
            "import_boundaries": [
                {
                    "id": "ui-no-server-imports",
                    "sources": ["apps/web/**", "packages/ui/**"],
                    "disallowed_imports": [
                        "server/**",
                        "packages/server/**",
                        "packages/domain/**",
                    ],
                    "allowed_imports": ["packages/domain/types/**"],
                    "severity": "warning",
                    "risk": (
                        "Cross-layer imports couple presentation code to implementation "
                        "details and make refactors unsafe."
                    ),
                    "expected": (
                        "Move access behind API/client/service boundaries or import only "
                        "stable shared types."
                    ),
                }
            ],
        }
    }


def test_architecture_rules_disabled_by_default(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / "apps/web/page.tsx", 'import db from "../../server/db";\n')
    _write(tmp_path / "server/db.ts", "export const db = {};\n")

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    assert not any(finding["category"] == "architecture" for finding in result["findings"])


def test_architecture_import_boundary_detects_forbidden_relative_import(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / "apps/web/page.tsx", 'import db from "../../server/db";\n')
    _write(tmp_path / "server/db.ts", "export const db = {};\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config=_ui_no_server_imports_config(),
    )

    architecture = [
        finding
        for finding in result["findings"]
        if finding["rule_id"] == "architecture-import-boundary:ui-no-server-imports"
    ]
    assert len(architecture) == 1
    finding = architecture[0]
    assert finding["file"] == "apps/web/page.tsx"
    assert finding["line"] == 1
    assert 'import db from "../../server/db";' in finding["evidence"]
    assert "Cross-layer imports" in finding["risk"]
    assert "stable shared types" in finding["expected_improvement"]


def test_architecture_import_boundary_respects_allowed_imports(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "apps/web/page.tsx",
        'import type { User } from "../../packages/domain/types/user";\n',
    )
    _write(tmp_path / "packages/domain/types/user.ts", "export type User = { id: string };\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config=_ui_no_server_imports_config(),
    )

    assert not any(finding["category"] == "architecture" for finding in result["findings"])


def test_architecture_pattern_boundary_detects_validator_side_effect(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "src/schemas/user.ts",
        "\n".join(
            [
                "export const userSchema = {",
                "  async validate() {",
                "    await fetch('/api/user');",
                "  },",
                "};",
            ]
        ),
    )

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={
            "architecture": {
                "enabled": True,
                "pattern_boundaries": [
                    {
                        "id": "validators-no-side-effects",
                        "paths": [
                            "**/schemas/**",
                            "**/*schema*.ts",
                            "**/*validator*.ts",
                            "**/*validation*.ts",
                        ],
                        "disallowed_patterns": [
                            r"\bawait\b",
                            r"\bfetch\s*\(",
                            r"\bprisma\.",
                            r"\bdb\.",
                            r"\bprocess\.env\.",
                            r"\breadFile\s*\(",
                            r"\bwriteFile\s*\(",
                        ],
                        "severity": "warning",
                        "risk": (
                            "Side effects inside validation make input contracts harder to "
                            "reuse, test, and reason about."
                        ),
                        "expected": (
                            "Keep validation modules declarative; move runtime work to "
                            "services or route handlers."
                        ),
                    }
                ],
            }
        },
    )

    architecture = [
        finding
        for finding in result["findings"]
        if finding["rule_id"].startswith("architecture-pattern-boundary:validators-no-side-effects")
    ]
    assert len(architecture) == 2
    assert {finding["line"] for finding in architecture} == {3}
    assert all("Side effects inside validation" in finding["risk"] for finding in architecture)


def test_architecture_findings_are_deterministic(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / "apps/web/a.tsx", 'import db from "../../server/db";\n')
    _write(tmp_path / "apps/web/b.tsx", 'import cache from "../../server/cache";\n')
    _write(tmp_path / "server/db.ts", "export const db = {};\n")
    _write(tmp_path / "server/cache.ts", "export const cache = {};\n")

    config = _ui_no_server_imports_config()
    first = create_code_quality_scan(tmp_path, scan={"run_id": "first"}, config=config)
    second = create_code_quality_scan(tmp_path, scan={"run_id": "second"}, config=config)

    first_keys = [
        (finding["file"], finding["line"], finding["rule_id"], finding["fingerprint"])
        for finding in first["findings"]
        if finding["category"] == "architecture"
    ]
    second_keys = [
        (finding["file"], finding["line"], finding["rule_id"], finding["fingerprint"])
        for finding in second["findings"]
        if finding["category"] == "architecture"
    ]

    assert first_keys == second_keys
    assert [item[0] for item in first_keys] == ["apps/web/a.tsx", "apps/web/b.tsx"]
