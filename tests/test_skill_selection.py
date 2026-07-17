from __future__ import annotations

import json
from pathlib import Path

from quality_runner.skill_selection import (
    load_selected_skills,
    repository_skill_signals,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _pack(*, pack_id: str, focus: str, pattern: str | None = None) -> str:
    rule = ""
    if pattern is not None:
        rule = f'''

[[deterministic_rules]]
id = "{pack_id}-rule"
type = "disallowed_pattern"
paths = ["**/*.tsx"]
message = "Keep the scoped code aligned with the selected standard."
risk = "The repository can drift from the selected standard."
expected = "Use the repository's declared standard."
disallowed_patterns = ["{pattern}"]
'''
    review = f'''

[[agent_reviews]]
id = "{pack_id}-review"
category = "quality"
severity = "observation"
paths = ["**/*.tsx"]
rubric = "Review the selected standard with concrete file and line evidence."
'''
    return f'''id = "{pack_id}"
name = "{pack_id.replace("-", " ").title()}"
version = "0.1.0"
description = "A {focus} quality standard."
{rule}{review}'''


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    _write(
        root / "packs/ui-foundations.toml",
        _pack(pack_id="ui-foundations", focus="ui visual components", pattern="<div[^>]+onClick="),
    )
    _write(
        root / "packs/security-privacy.toml",
        _pack(pack_id="security-privacy", focus="security privacy authorization"),
    )
    _write(
        root / "quality-runner-corpus.toml",
        """schema = "quality-runner-skill-corpus-v0.1"
id = "personal"
version = "0.1.0"
active = ["ui-foundations", "security-privacy"]

[[packs]]
id = "ui-foundations"
path = "packs/ui-foundations.toml"
focus = ["ui", "visual", "components"]

[[packs]]
id = "security-privacy"
path = "packs/security-privacy.toml"
focus = ["security", "privacy", "authorization"]
""",
    )
    return root


def _global_config(tmp_path: Path, corpus: Path, *, extra: str = "") -> Path:
    path = tmp_path / "global" / "quality-runner.toml"
    _write(
        path,
        f'''schema = "quality-runner-global-skill-config-v0.1"

[quality_runner.skills]
enabled = true
corpus = "{corpus}"
mode = "relevant"
min_score = 0.2
max_active = 12
{extra}
''',
    )
    return path


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "package.json", '{"name":"fixture"}\n')
    _write(repo / "src/components/Page.tsx", "export const Page = () => <div onClick={open} />;\n")
    return repo


def test_global_corpus_selects_relevant_packs_and_records_reasons(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    corpus = _corpus(tmp_path)
    config_path = _global_config(tmp_path, corpus)
    signals = repository_skill_signals(repo, [{"path": "src/components/Page.tsx"}])

    skills, warnings, selection = load_selected_skills(
        repo,
        {},
        repo_signals=signals,
        global_config_path=config_path,
    )

    assert warnings == []
    assert [skill["id"] for skill in skills] == ["ui-foundations"]
    assert selection["status"] == "enabled"
    assert selection["source"] == "global"
    assert selection["selected_global_skill_ids"] == ["ui-foundations"]
    candidates = {item["id"]: item for item in selection["candidates"]}
    assert candidates["ui-foundations"]["status"] == "selected"
    assert candidates["ui-foundations"]["matched_terms"]
    assert candidates["security-privacy"]["status"] == "not-relevant"

    replay_signals = [*([str(index) for index in range(300)]), *selection["repo_signals"]]
    replayed_skills, replay_warnings, replayed_selection = load_selected_skills(
        repo,
        {},
        repo_signals=replay_signals,
        global_config_path=config_path,
    )
    assert replay_warnings == []
    assert [skill["id"] for skill in replayed_skills] == ["ui-foundations"]
    assert replayed_selection["selected_global_skill_ids"] == ["ui-foundations"]


def test_global_selection_respects_pins_and_exclusions(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    corpus = _corpus(tmp_path)
    config_path = _global_config(
        tmp_path,
        corpus,
        extra='always = ["security-privacy"]\nexclude = ["ui-foundations"]\n',
    )

    skills, warnings, selection = load_selected_skills(
        repo,
        {},
        repo_signals=["typescript", "components"],
        global_config_path=config_path,
    )

    assert warnings == []
    assert [skill["id"] for skill in skills] == ["security-privacy"]
    candidates = {item["id"]: item for item in selection["candidates"]}
    assert candidates["security-privacy"]["reason"] == "explicitly pinned"
    assert candidates["ui-foundations"]["status"] == "excluded"


def test_repository_can_disable_global_corpus(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    corpus = _corpus(tmp_path)
    config_path = _global_config(tmp_path, corpus)

    skills, warnings, selection = load_selected_skills(
        repo,
        {"skills": {"global_enabled": False}},
        repo_signals=["typescript", "components"],
        global_config_path=config_path,
    )

    assert skills == []
    assert warnings == []
    assert selection["status"] == "disabled"
    assert selection["source"] == "repository"


def test_normal_scan_uses_global_corpus_and_keeps_selection_json_safe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    repo = _repo(tmp_path)
    corpus = _corpus(tmp_path)
    config_path = _global_config(tmp_path, corpus)
    monkeypatch.setenv("QUALITY_RUNNER_GLOBAL_CONFIG", str(config_path))

    scan = create_code_quality_scan(repo, scan={"run_id": "global-skills"}, config={})

    assert scan["skill_selection"]["selected_global_skill_ids"] == ["ui-foundations"]
    assert any(
        finding["rule_id"] == "ui-foundations/ui-foundations-rule" for finding in scan["findings"]
    )
    json.dumps(scan)


def test_workflow_artifact_and_module_status_expose_global_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from quality_runner.workflow import run_payload

    repo = _repo(tmp_path)
    corpus = _corpus(tmp_path)
    config_path = _global_config(tmp_path, corpus)
    monkeypatch.setenv("QUALITY_RUNNER_GLOBAL_CONFIG", str(config_path))

    payload = run_payload(repo, run_id="global-workflow")
    run_dir = repo / ".quality-runner" / "runs" / "global-workflow"
    scan = json.loads((run_dir / "code-quality-scan.json").read_text(encoding="utf-8"))

    assert payload["module_status"]["modules"]
    quality_skills = next(
        item for item in payload["module_status"]["modules"] if item["id"] == "quality-skills"
    )
    assert quality_skills["status"] == "enabled"
    assert scan["skill_selection"]["selected_skill_ids"] == ["ui-foundations"]
    assert payload["skill_review"]["packet_json"]
    assert Path(payload["skill_review"]["packet_json"]).exists()
