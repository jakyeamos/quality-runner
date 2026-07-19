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


def test_unwired_scan_ignores_test_only_references() -> None:
    from quality_runner.code_quality_unwired import unwired_findings

    definition = {
        "path": "src/feature.ts",
        "text": "export function Feature() {}\n",
        "lines": ["export function Feature() {}"],
    }
    test_reference = {
        "path": "tests/feature.test.ts",
        "text": "Feature();\n",
        "lines": ["Feature();"],
    }

    findings = unwired_findings([definition, test_reference], {})
    assert any(finding["rule_id"] == "export-without-references" for finding in findings)

    consumer = {
        "path": "src/consumer.ts",
        "text": "Feature();\n",
        "lines": ["Feature();"],
    }
    findings = unwired_findings([definition, test_reference, consumer], {})
    assert all(finding["rule_id"] != "export-without-references" for finding in findings)


def test_reference_index_scans_each_non_test_file_once(monkeypatch) -> None:
    from quality_runner import code_quality_unwired

    original_pattern = code_quality_unwired._SYMBOL_REFERENCE_RE
    calls = 0

    class CountingPattern:
        def finditer(self, text: str):
            nonlocal calls
            calls += 1
            return original_pattern.finditer(text)

    monkeypatch.setattr(code_quality_unwired, "_SYMBOL_REFERENCE_RE", CountingPattern())
    source_files = [
        {
            "path": f"src/file-{index}.ts",
            "text": f"export const Symbol{index} = {index};\n",
            "lines": [f"export const Symbol{index} = {index};"],
        }
        for index in range(20)
    ]
    source_files.append(
        {
            "path": "tests/file.test.ts",
            "text": "Symbol1();\n",
            "lines": ["Symbol1();"],
        }
    )

    reference_index = code_quality_unwired._build_reference_index(source_files)

    assert calls == 20
    assert reference_index.paths_by_symbol["Symbol1"] == frozenset({"src/file-1.ts"})


def test_reference_index_summarizes_registration_paths_once() -> None:
    from quality_runner import code_quality_unwired

    source_files = [
        {
            "path": "src/feature.ts",
            "text": "export function Feature() {}\n",
            "lines": ["export function Feature() {}"],
        },
        {
            "path": "src/router.ts",
            "text": "register(Feature);\n",
            "lines": ["register(Feature);"],
        },
    ]

    reference_index = code_quality_unwired._build_reference_index(
        source_files,
        registration_paths={"src/router.ts"},
    )

    assert reference_index.registration_paths_by_symbol["Feature"] == frozenset({"src/router.ts"})
