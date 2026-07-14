from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quality_runner.schema_constants import (
    PLAN_CONFIG_SCHEMA,
    PLANNING_STATE_SCHEMA,
    ROADMAP_SCHEMA,
)

PLAN_ROOT_NAME = "quality-runner"
PLAN_ROOT_RELATIVE = Path(".planning") / PLAN_ROOT_NAME
PLAN_MARKER = "quality-runner-plan-json"
ROADMAP_MARKER = "quality-runner-roadmap-json"
STATE_MARKER = "quality-runner-state-json"
VERIFICATION_MARKER = "quality-runner-verification-json"
MACHINE_BLOCK_PATTERN = re.compile(
    r"(?P<start><!-- (?P<marker>[a-z0-9-]+):start -->\n)"
    r"(?P<body>.*?)"
    r"(?P<end><!-- (?P=marker):end -->)",
    re.DOTALL,
)


def plan_root(repo_root: Path) -> Path:
    root = repo_root.expanduser().resolve()
    planning_root = root / ".planning"
    target = planning_root / PLAN_ROOT_NAME
    _reject_symlink(planning_root, ".planning")
    _reject_symlink(target, str(PLAN_ROOT_RELATIVE))
    return target


def require_plan_root(repo_root: Path) -> Path:
    root = plan_root(repo_root)
    if not root.exists():
        raise FileNotFoundError(f"QR planning is not initialized: {root}")
    if not root.is_dir():
        raise ValueError(f"QR planning root is not a directory: {root}")
    return root


def initialize_plan_root(repo_root: Path) -> dict[str, Any]:
    root = plan_root(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    phases_dir = root / "phases"
    _reject_symlink(phases_dir, str(PLAN_ROOT_RELATIVE / "phases"))
    phases_dir.mkdir(exist_ok=True)
    created: list[str] = []
    config_path = root / "config.json"
    if not config_path.exists():
        _write_json(
            config_path,
            {
                "schema": PLAN_CONFIG_SCHEMA,
                "format": "quality-runner-planning-v0.1",
                "commit_docs": True,
            },
        )
        created.append(str(config_path))
    roadmap_path = root / "ROADMAP.md"
    if not roadmap_path.exists():
        _write_machine_document(
            roadmap_path,
            ROADMAP_MARKER,
            {"schema": ROADMAP_SCHEMA, "status": "active", "phases": []},
            "# Quality Runner Roadmap\n\n## Phases\n\n- No phases yet.\n",
        )
        created.append(str(roadmap_path))
    state_path = root / "STATE.md"
    if not state_path.exists():
        _write_machine_document(
            state_path,
            STATE_MARKER,
            {
                "schema": PLANNING_STATE_SCHEMA,
                "status": "ready",
                "current_phase": None,
                "last_action": "plan-init",
                "updated_at": _now(),
                "unplanned_findings": [],
            },
            "# Quality Runner Planning State\n\n## Workflow Notes\n\n- QR planning is advisory-only.\n- Source changes, commits, and pushes remain external.\n",
        )
        created.append(str(state_path))
    return {"root": str(root), "created": created, "paths": _root_paths(root)}


def load_config(repo_root: Path) -> dict[str, Any]:
    root = require_plan_root(repo_root)
    return _load_json(root / "config.json", PLAN_CONFIG_SCHEMA)


def load_roadmap(repo_root: Path) -> dict[str, Any]:
    root = require_plan_root(repo_root)
    return _load_machine_document(root / "ROADMAP.md", ROADMAP_MARKER, ROADMAP_SCHEMA)


def save_roadmap(repo_root: Path, roadmap: dict[str, Any]) -> Path:
    root = require_plan_root(repo_root)
    path = root / "ROADMAP.md"
    content = _replace_machine_block(
        path.read_text(encoding="utf-8"), ROADMAP_MARKER, roadmap
    )
    path.write_text(content, encoding="utf-8")
    return path


def load_state(repo_root: Path) -> dict[str, Any]:
    root = require_plan_root(repo_root)
    return _load_machine_document(root / "STATE.md", STATE_MARKER, PLANNING_STATE_SCHEMA)


def save_state(repo_root: Path, state: dict[str, Any]) -> Path:
    root = require_plan_root(repo_root)
    path = root / "STATE.md"
    content = _replace_machine_block(path.read_text(encoding="utf-8"), STATE_MARKER, state)
    path.write_text(content, encoding="utf-8")
    return path


def phase_directory(repo_root: Path, phase_number: int) -> Path:
    if phase_number < 1:
        raise ValueError("phase number must be at least 1")
    roadmap = load_roadmap(repo_root)
    phase = phase_by_number(roadmap, phase_number)
    root = require_plan_root(repo_root)
    phases_root = root / "phases"
    _reject_symlink(phases_root, str(PLAN_ROOT_RELATIVE / "phases"))
    target = phases_root / f"{phase_number:02d}-{phase['slug']}"
    _reject_symlink(target, str(target.relative_to(root)))
    return target


def phase_by_number(roadmap: dict[str, Any], phase_number: int) -> dict[str, Any]:
    phases = roadmap.get("phases")
    if not isinstance(phases, list):
        raise ValueError("QR roadmap phases must be a list")
    for phase in phases:
        if isinstance(phase, dict) and phase.get("number") == phase_number:
            return phase
    raise FileNotFoundError(f"QR phase does not exist: {phase_number:02d}")


def plan_file(repo_root: Path, phase_number: int, plan_number: int) -> Path:
    directory = phase_directory(repo_root, phase_number)
    return directory / f"{phase_number:02d}-{plan_number:02d}-PLAN.md"


def summary_file(repo_root: Path, phase_number: int, plan_number: int) -> Path:
    directory = phase_directory(repo_root, phase_number)
    return directory / f"{phase_number:02d}-{plan_number:02d}-SUMMARY.md"


def verification_file(repo_root: Path, phase_number: int) -> Path:
    return phase_directory(repo_root, phase_number) / f"{phase_number:02d}-VERIFICATION.md"


def load_phase_plans(repo_root: Path, phase_number: int) -> list[dict[str, Any]]:
    directory = phase_directory(repo_root, phase_number)
    plans: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*-PLAN.md")):
        plans.append(load_plan_file(path))
    return sorted(plans, key=lambda item: int(item["plan"]))


def load_plan_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"QR plan does not exist: {path}")
    payload = _load_machine_document(path, PLAN_MARKER, "quality-runner-phase-plan-v0.1")
    payload["path"] = str(path)
    return payload


def update_plan_file(path: Path, payload: dict[str, Any]) -> Path:
    document_payload = {key: value for key, value in payload.items() if key != "path"}
    content = _replace_machine_block(
        path.read_text(encoding="utf-8"), PLAN_MARKER, document_payload
    )
    path.write_text(content, encoding="utf-8")
    return path


def write_verification_file(path: Path, payload: dict[str, Any], body: str) -> Path:
    if path.exists():
        content = _replace_machine_block(path.read_text(encoding="utf-8"), VERIFICATION_MARKER, payload)
    else:
        content = _machine_block(VERIFICATION_MARKER, payload) + "\n" + body
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_summary_file(path: Path, payload: dict[str, Any], body: str) -> Path:
    content = _machine_block("quality-runner-batch-result-json", payload) + "\n" + body
    path.write_text(content, encoding="utf-8")
    return path


def _root_paths(root: Path) -> dict[str, str]:
    return {
        "root": str(root),
        "roadmap": str(root / "ROADMAP.md"),
        "state": str(root / "STATE.md"),
        "config": str(root / "config.json"),
        "phases": str(root / "phases"),
    }


def _load_machine_document(path: Path, marker: str, schema: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"QR planning file does not exist: {path}")
    match = _machine_match(path.read_text(encoding="utf-8"), marker)
    if match is None:
        raise ValueError(f"QR planning file is missing its machine block: {path}")
    payload = json.loads(match.group("body"))
    if not isinstance(payload, dict) or payload.get("schema") != schema:
        raise ValueError(f"QR planning file has an invalid schema: {path}")
    return payload


def _load_json(path: Path, schema: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"QR planning file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != schema:
        raise ValueError(f"QR planning file has an invalid schema: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_machine_document(
    path: Path, marker: str, payload: dict[str, Any], body: str
) -> None:
    path.write_text(_machine_block(marker, payload) + "\n" + body, encoding="utf-8")


def _machine_block(marker: str, payload: dict[str, Any]) -> str:
    return (
        f"<!-- {marker}:start -->\n"
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n"
        f"<!-- {marker}:end -->"
    )


def _replace_machine_block(content: str, marker: str, payload: dict[str, Any]) -> str:
    match = _machine_match(content, marker)
    block = _machine_block(marker, payload)
    if match is None:
        return block + "\n\n" + content.lstrip()
    return content[: match.start()] + block + content[match.end() :]


def _machine_match(content: str, marker: str) -> re.Match[str] | None:
    for match in MACHINE_BLOCK_PATTERN.finditer(content):
        if match.group("marker") == marker:
            return match
    return None


def _reject_symlink(path: Path, label: str) -> None:
    if path.is_symlink():
        raise ValueError(f"QR planning path must not be a symlink: {label}")


def _now() -> str:
    return datetime.now(UTC).isoformat()
