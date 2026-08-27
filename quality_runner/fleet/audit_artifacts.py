from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_FLEET_ROOT = Path("~/.quality-runner/fleet-audit")


def artifact_root(output_dir: Path | None, audit_id: str, *, local: bool = False) -> Path:
    if output_dir is not None:
        base = output_dir.expanduser().resolve()
        return base if base.name == audit_id else base / audit_id
    base = DEFAULT_FLEET_ROOT.expanduser().resolve()
    return base / (f"local/{audit_id}" if local else audit_id)


def resolve_artifact_root(output_dir: Path | None, audit_id: str | None) -> Path:
    if output_dir is not None:
        candidate = output_dir.expanduser().resolve()
        if (candidate / "inventory.json").is_file():
            return candidate
        if audit_id:
            return candidate / audit_id
        return latest_audit(candidate)
    base = DEFAULT_FLEET_ROOT.expanduser().resolve()
    if audit_id:
        direct = base / audit_id
        if direct.is_dir():
            return direct
        local = base / "local" / audit_id
        if local.is_dir():
            return local
    return latest_audit(base)


def latest_audit(root: Path) -> Path:
    candidates = [path for path in root.glob("**/inventory.json") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"no fleet audit artifacts found under {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime).parent


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
