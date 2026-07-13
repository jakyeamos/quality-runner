from __future__ import annotations

import tomllib
from pathlib import Path

from quality_runner.skill_corpus import (
    append_skill_to_corpus,
    classify_skill_pack,
    load_skill_corpus,
    sync_skill_corpus,
)


def _pack_toml(*, pack_id: str, name: str, description: str) -> str:
    return f'''id = "{pack_id}"
name = "{name}"
version = "0.1.0"
description = "{description}"

[[deterministic_rules]]
id = "existing-rule"
type = "disallowed_pattern"
paths = ["src/**/*.tsx"]
message = "Avoid inaccessible visual treatment."
risk = "Users can miss important UI state."
expected = "Use accessible visual patterns."
disallowed_patterns = ["outline: none"]
category = "accessibility"
'''


def _candidate_toml() -> str:
    return """id = "raw-visual-skill"
name = "Accessible component states"
version = "0.2.0"
description = "Review accessible visual components and interaction states."

[[deterministic_rules]]
id = "component-state-rule"
type = "disallowed_pattern"
paths = ["src/**/*.tsx"]
message = "Do not hide focus state on interactive components."
risk = "Keyboard users can lose their place."
expected = "Preserve visible accessible focus treatment."
disallowed_patterns = ["outline: none"]
category = "accessibility"
"""


def _write_corpus(tmp_path: Path) -> tuple[Path, Path]:
    corpus_root = tmp_path / "personal-corpus"
    pack_path = corpus_root / "packs/ui-foundations.toml"
    pack_path.parent.mkdir(parents=True)
    pack_path.write_text(
        _pack_toml(
            pack_id="ui-foundations",
            name="UI Foundations",
            description="Visual hierarchy, accessibility, and component states.",
        ),
        encoding="utf-8",
    )
    manifest_path = corpus_root / "quality-runner-corpus.toml"
    manifest_path.write_text(
        """schema = "quality-runner-skill-corpus-v0.1"
id = "personal"
version = "0.1.0"
active = ["ui-foundations"]

[[packs]]
id = "ui-foundations"
path = "packs/ui-foundations.toml"
focus = ["ui", "visual", "accessibility", "components"]
""",
        encoding="utf-8",
    )
    return corpus_root, manifest_path


def test_corpus_load_and_classification_recommend_existing_pack(tmp_path: Path) -> None:
    corpus_root, manifest_path = _write_corpus(tmp_path)
    candidate = tmp_path / "candidate.toml"
    candidate.write_text(_candidate_toml(), encoding="utf-8")

    corpus, errors = load_skill_corpus(corpus_root)
    result = classify_skill_pack(
        candidate,
        skill_id="raw-visual-skill",
        corpus_path=manifest_path,
    )

    assert errors == []
    assert corpus is not None
    assert result["status"] == "classified"
    assert result["recommended_pack_id"] == "ui-foundations"
    assert result["recommendations"][0]["fit"] == "likely"


def test_append_namespaces_rules_and_records_provenance(tmp_path: Path) -> None:
    corpus_root, manifest_path = _write_corpus(tmp_path)
    target_pack = corpus_root / "packs/ui-foundations.toml"
    candidate = tmp_path / "candidate.toml"
    candidate.write_text(_candidate_toml(), encoding="utf-8")
    before = target_pack.read_text(encoding="utf-8")

    preview = append_skill_to_corpus(
        candidate,
        source_skill_id="raw-visual-skill",
        pack_id="ui-foundations",
        corpus_path=manifest_path,
        source_ref="personal/.codex/skills/accessible-components",
    )

    assert preview["status"] == "validated"
    assert target_pack.read_text(encoding="utf-8") == before

    result = append_skill_to_corpus(
        candidate,
        source_skill_id="raw-visual-skill",
        pack_id="ui-foundations",
        corpus_path=manifest_path,
        source_ref="personal/.codex/skills/accessible-components",
        write=True,
    )

    merged = tomllib.loads(target_pack.read_text(encoding="utf-8"))
    assert result["status"] == "appended"
    assert merged["sources"][0]["id"] == "raw-visual-skill"
    assert merged["sources"][0]["ref"] == "personal/.codex/skills/accessible-components"
    assert "raw-visual-skill/component-state-rule" in {
        rule["id"] for rule in merged["deterministic_rules"]
    }
    assert result["corpus_path"] == str(manifest_path)


def test_sync_is_dry_run_by_default_and_preserves_target_only_skills(tmp_path: Path) -> None:
    corpus_root, manifest_path = _write_corpus(tmp_path)
    source_before = (corpus_root / "packs/ui-foundations.toml").read_text(encoding="utf-8")
    repo_one = tmp_path / "repo-one"
    repo_two = tmp_path / "repo-two"
    for repo in (repo_one, repo_two):
        repo.mkdir()
    (repo_one / ".quality-runner.toml").write_text(
        """[quality_runner.artifacts]
retention_runs = 4

[quality_runner.skills]
enabled = true
active = ["legacy"]

[[quality_runner.skills.local]]
id = "legacy"
path = ".quality-runner/skills/legacy.toml"
""",
        encoding="utf-8",
    )

    dry_run = sync_skill_corpus(
        manifest_path,
        repo_roots=[repo_one, repo_two],
    )

    assert dry_run["status"] == "planned"
    assert not (repo_one / ".quality-runner/skills/ui-foundations.toml").exists()
    assert not (repo_two / ".quality-runner.toml").exists()

    applied = sync_skill_corpus(
        manifest_path,
        repo_roots=[repo_one, repo_two],
        write=True,
    )

    assert applied["status"] == "synchronized"
    assert source_before == (corpus_root / "packs/ui-foundations.toml").read_text(encoding="utf-8")
    config_one = (repo_one / ".quality-runner.toml").read_text(encoding="utf-8")
    assert "retention_runs = 4" in config_one
    assert 'id = "legacy"' in config_one
    assert 'id = "ui-foundations"' in config_one
    assert 'active = ["legacy", "ui-foundations"]' in config_one
    assert (repo_two / ".quality-runner/skills/ui-foundations.toml").exists()


def test_corpus_rejects_manifest_path_traversal(tmp_path: Path) -> None:
    manifest = tmp_path / "quality-runner-corpus.toml"
    manifest.write_text(
        """schema = "quality-runner-skill-corpus-v0.1"
id = "personal"

[[packs]]
id = "unsafe"
path = "../outside.toml"
""",
        encoding="utf-8",
    )

    corpus, errors = load_skill_corpus(manifest)

    assert corpus is None
    assert any("traversal safety" in error for error in errors)
