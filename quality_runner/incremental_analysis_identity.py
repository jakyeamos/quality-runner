from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path

_DEPENDENCY_FILE_NAMES = frozenset(
    {
        "Cargo.lock",
        "Cargo.toml",
        "Gemfile",
        "Gemfile.lock",
        "Pipfile",
        "Pipfile.lock",
        "composer.json",
        "composer.lock",
        "go.mod",
        "go.sum",
        "package-lock.json",
        "package.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pyproject.toml",
        "requirements.txt",
        "uv.lock",
        "yarn.lock",
    }
)
_SKIPPED_STATE_DIRECTORIES = frozenset(
    {".git", ".quality-runner", "node_modules", ".venv", "__pycache__"}
)


def configuration_identity(repo_root: Path, config: Mapping[str, object]) -> str:
    return _json_hash(
        {
            "config": config,
            "local_rule_files": _state_file_digests(repo_root / ".quality-runner" / "skills"),
            "global_rule_sources": _global_rule_source_digests(),
        }
    )


def dependency_state_identity(repo_root: Path) -> str:
    return _json_hash({"dependency_files": _named_file_digests(repo_root)})


def scanner_implementation_identity() -> str:
    package_root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(package_root.rglob("*.py")):
        if any(part == "__pycache__" for part in path.parts):
            continue
        try:
            digest.update(path.relative_to(package_root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        except OSError:
            digest.update(f"unreadable:{path}".encode())
    return digest.hexdigest()


def _global_rule_source_digests() -> list[dict[str, str]]:
    digests: list[dict[str, str]] = []
    for variable in ("QUALITY_RUNNER_GLOBAL_CONFIG", "QUALITY_RUNNER_SKILL_CORPUS"):
        value = os.environ.get(variable)
        if not value:
            continue
        path = Path(value).expanduser().resolve()
        digests.extend(_state_file_digests(path, prefix=variable))
    from quality_runner.skill_selection import load_global_skill_config

    global_config, _warnings = load_global_skill_config()
    if global_config is not None:
        for key in ("path", "corpus_path"):
            value = global_config.get(key)
            if isinstance(value, str):
                path = Path(value).expanduser().resolve()
            elif isinstance(value, Path):
                path = value.expanduser().resolve()
            else:
                continue
            digests.extend(_state_file_digests(path, prefix=f"global:{key}"))
    return digests


def _named_file_digests(root: Path) -> list[dict[str, str]]:
    if not root.is_dir():
        return []
    digests: list[dict[str, str]] = []
    for current_root, dir_names, file_names in os.walk(root):
        dir_names[:] = sorted(name for name in dir_names if name not in _SKIPPED_STATE_DIRECTORIES)
        current = Path(current_root)
        for name in sorted(file_names):
            if name not in _DEPENDENCY_FILE_NAMES:
                continue
            path = current / name
            digest = _file_digest(path)
            if digest is not None:
                digests.append({"path": path.relative_to(root).as_posix(), "sha256": digest})
    return digests


def _state_file_digests(path: Path, *, prefix: str | None = None) -> list[dict[str, str]]:
    if path.is_file():
        digest = _file_digest(path)
        return [{"path": f"{prefix}:{path}", "sha256": digest}] if digest is not None else []
    if not path.is_dir():
        return []
    digests: list[dict[str, str]] = []
    for current_root, dir_names, file_names in os.walk(path):
        dir_names[:] = sorted(name for name in dir_names if name not in _SKIPPED_STATE_DIRECTORIES)
        current = Path(current_root)
        for name in sorted(file_names):
            file_path = current / name
            digest = _file_digest(file_path)
            if digest is not None:
                relative = file_path.relative_to(path).as_posix()
                digests.append(
                    {
                        "path": f"{prefix}:{relative}" if prefix else relative,
                        "sha256": digest,
                    }
                )
    return digests


def _file_digest(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _json_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()
