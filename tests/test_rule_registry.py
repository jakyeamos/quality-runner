from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from quality_runner.rule_registry import (
    BUILTIN_CODE_QUALITY_RULES,
    BUILTIN_RULE_TEST_EVIDENCE,
    DYNAMIC_RULE_FAMILIES,
    rule_registry,
)

ROOT = Path(__file__).resolve().parents[1]


def _literal_rule_ids() -> set[str]:
    values: set[str] = set()
    for source in (ROOT / "quality_runner").glob("code_quality*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "rule_id"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    values.add(value.value)
    return values


def test_registry_covers_every_literal_builtin_and_declares_dynamic_families() -> None:
    # configured-disposition is a resolution-ledger row, not a scanner finding.
    assert _literal_rule_ids() - {"configured-disposition"} <= BUILTIN_CODE_QUALITY_RULES
    assert len(BUILTIN_CODE_QUALITY_RULES) == 74
    assert len(DYNAMIC_RULE_FAMILIES) == 5


def test_every_exact_rule_has_explicit_three_class_qualification_state() -> None:
    payload = rule_registry(ROOT)
    assert len(payload["exact_rules"]) == payload["summary"]["exact_rule_count"]
    for rule in payload["exact_rules"]:
        verification = rule["verification"]
        covered = {item.split(":", 1)[0] for item in verification["evidence_refs"]}
        missing = set(verification["missing_evidence"])
        assert covered | missing == {"positive", "negative", "boundary"}
        assert not (covered & missing)
        assert (verification["status"] == "behavior-verified") == (not missing)


def test_unverified_rule_cannot_be_silently_described_as_qualified() -> None:
    assert set(BUILTIN_RULE_TEST_EVIDENCE) <= BUILTIN_CODE_QUALITY_RULES
    payload = rule_registry(ROOT)
    verified = {
        rule["rule_id"]
        for rule in payload["exact_rules"]
        if rule["verification"]["status"] == "behavior-verified"
    }
    assert verified == {"large-source-file", "nested-ternary"}
    assert payload["summary"]["unverified_exact_rule_count"] == 72


def test_registry_includes_repository_active_skill_pack_rules(tmp_path: Path) -> None:
    skill = tmp_path / ".quality-runner/skills/ui.toml"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """id = "ui"
name = "UI"
[[deterministic_rules]]
id = "click-target"
type = "disallowed_pattern"
category = "accessibility"
severity = "warning"
paths = ["**/*.tsx"]
disallowed_patterns = ["onClick"]
message = "Use semantics."
risk = "Keyboard access."
expected = "Use a button."
verification = "Rerun QR."
[[agent_reviews]]
id = "polish-review"
category = "ui"
severity = "observation"
paths = ["**/*.tsx"]
focus = ["states"]
rubric = "Review states."
""",
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        """[quality_runner.skills]
enabled = true
active = ["ui"]
[[quality_runner.skills.local]]
id = "ui"
path = ".quality-runner/skills/ui.toml"
""",
        encoding="utf-8",
    )

    payload = rule_registry(tmp_path)
    rules = {item["rule_id"] for item in payload["exact_rules"]}
    assert {"ui/click-target", "ui/polish-review"} <= rules
    assert payload["summary"]["skill_pack_exact_rule_count"] == 2


def test_rule_registry_cli_is_machine_readable() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "rules", "registry", str(ROOT), "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["schema"] == "quality-runner-rule-registry/v1"
    assert payload["summary"]["builtin_exact_rule_count"] == 74


def test_rule_registry_schema_accepts_live_payload() -> None:
    schema = json.loads(
        (ROOT / "quality_runner/schemas/rule-registry.schema.json").read_text(encoding="utf-8")
    )
    payload = rule_registry(ROOT)
    assert schema["properties"]["schema"]["const"] == payload["schema"]
    assert set(schema["required"]) <= set(payload)
    assert set(schema["properties"]["summary"]["required"]) <= set(payload["summary"])
