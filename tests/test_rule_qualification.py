from __future__ import annotations

from pathlib import Path

from quality_runner.code_quality import create_code_quality_scan
from quality_runner.rule_registry import BUILTIN_CODE_QUALITY_RULES


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _builtin_findings(root: Path) -> set[str]:
    result = create_code_quality_scan(
        root,
        scan={"run_id": "rule-qualification"},
        config={"structural_scan": {"similarity_enabled": False}},
    )
    return {
        str(item["rule_id"])
        for item in result["findings"]
        if str(item.get("rule_id")) in BUILTIN_CODE_QUALITY_RULES
    }


def test_previously_uncovered_builtin_rules_have_positive_fixtures(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "component.tsx",
        "// @ts-ignore\n"
        "export const Unsafe = ({ html }) => "
        "<section dangerouslySetInnerHTML={{ __html: html }} />;\n",
    )
    _write(
        tmp_path / "src" / "styles.css",
        ".spinner { animation: spin 1s linear infinite; transition: opacity 200ms; }\n",
    )

    assert {
        "missing-reduced-motion",
        "ts-ignore",
        "unsafe-html-injection",
    } <= _builtin_findings(tmp_path)


def test_builtin_rules_stay_quiet_for_safe_multilanguage_corpus(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "service.py",
        "result: int = 1 + 1\n",
    )
    _write(
        tmp_path / "src" / "component.tsx",
        "const Greeting = ({ name }: { name: string }) => <p>Hello {name}</p>;\n"
        'const page = <Greeting name="Ada" />;\nvoid page;\n',
    )
    _write(tmp_path / "src" / "styles.css", ".label { color: currentColor; padding: 8px; }\n")
    _write(tmp_path / "tests" / "test_service.py", "def test_result():\n    assert 1 + 1 == 2\n")

    assert _builtin_findings(tmp_path) == set()


def test_builtin_rules_ignore_finding_rich_generated_scope(tmp_path: Path) -> None:
    generated = tmp_path / "src" / "generated"
    _write(
        generated / "unsafe.tsx",
        "// @ts-ignore\n"
        "const value: any = {};\n"
        "export const Unsafe = ({ html, onOpen }) => "
        "<div onClick={onOpen} dangerouslySetInnerHTML={{ __html: html }} />;\n",
    )
    _write(
        generated / "styles.css",
        ".spinner { animation: spin 1s linear infinite; transition: opacity 200ms; "
        "outline: none; z-index: 9999; }\n",
    )

    assert _builtin_findings(tmp_path) == set()
