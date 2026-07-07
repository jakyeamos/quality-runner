from __future__ import annotations

from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_code_quality_scan_detects_unwired_work_signals(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "src" / "draft_feature.py",
        "\n".join(
            [
                "def draft_feature():",
                "    raise NotImplementedError('wire this later')",
                "",
                "def lonely_service():",
                "    return 1",
            ]
        ),
    )
    _write(
        tmp_path / "src" / "commands.py",
        "\n".join(
            [
                "def handle_draft_command():",
                "    return 'draft'",
            ]
        ),
    )
    _write(tmp_path / "cli.py", "def main():\n    return 0\n")
    _write(
        tmp_path / "apps" / "web" / "src" / "app" / "draft" / "page.tsx",
        "\n".join(
            [
                "// TODO: finish loading state",
                "// TODO: connect action",
                "// FIXME: replace temporary copy",
                "export function DraftPage() {",
                "  return <main>draft placeholder</main>;",
                "}",
            ]
        ),
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    integrate = [finding for finding in result["findings"] if finding["category"] == "integrate"]
    rules = {finding["rule_id"] for finding in integrate}
    assert {
        "stub-implementation",
        "todo-scaffold",
        "export-without-references",
        "handler-without-registration",
    } <= rules
    assert result["summary"]["findings_by_category"]["integrate"] >= 4
    assert all(
        finding["remediation_bucket"] == "Integration and wiring decisions" for finding in integrate
    )


def test_code_quality_scan_can_disable_integrate_group(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "src" / "draft_feature.py",
        "def draft_feature():\n    raise NotImplementedError('later')\n",
    )

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={"integrate": {"enabled": False}},
    )

    assert all(finding["category"] != "integrate" for finding in result["findings"])
