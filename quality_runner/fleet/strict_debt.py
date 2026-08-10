"""Static maturity evidence for an occurrence-aware strict type baseline."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from quality_runner.strict_baseline import STRICT_BASELINE_SCHEMA

STRICT_CONFIG_PATH = Path("pyrightconfig.strict.json")
STRICT_BASELINE_PATH = Path("docs/baselines/basedpyright-strict.json")
_STRICT_TRUE = re.compile(r"(?im)(?:[\"']strict[\"']?|\bstrict)\s*[:=]\s*true\b")


def assess_strict_policy_visibility(root: Path, scan: dict[str, Any]) -> dict[str, Any]:
    """Assess visible strict-policy configuration across supported ecosystems."""

    surfaces = _strict_policy_surfaces(root, scan)
    if not surfaces:
        return {
            "score": None,
            "status": "not_applicable",
            "message": "No supported strict-capable type surface was found.",
            "evidence": [
                {
                    "path": ".",
                    "detail": "No BasedPyright, Pyright, mypy, or TypeScript surface was found.",
                }
            ],
        }
    score = min(int(item["score"]) for item in surfaces)
    if any(item["status"] == "blocked" for item in surfaces):
        status = "blocked"
    elif any(item["status"] == "absent" for item in surfaces):
        status = "absent"
    elif score >= 3:
        status = "validated"
    else:
        status = "discoverable"
    providers = ", ".join(str(item["provider"]) for item in surfaces)
    return {
        "score": score,
        "status": status,
        "message": (
            f"Strict-policy visibility across {providers}: "
            + "; ".join(str(item["message"]) for item in surfaces)
        ),
        "evidence": [evidence for item in surfaces for evidence in item["evidence"]],
    }


def _strict_policy_surfaces(root: Path, scan: dict[str, Any]) -> list[dict[str, Any]]:
    surfaces: list[dict[str, Any]] = []
    based_config = root / STRICT_CONFIG_PATH
    based_surface = _command_surface(scan, "basedpyright") or _text_contains(
        root / "pyproject.toml", "[tool.basedpyright]"
    )
    if based_config.is_file() and not based_config.is_symlink():
        surfaces.append(_basedpyright_surface(based_config, root / STRICT_BASELINE_PATH))
    elif based_surface:
        surfaces.append(_missing_strict_surface("BasedPyright", str(STRICT_CONFIG_PATH)))

    pyright_config = root / "pyrightconfig.json"
    if pyright_config.is_file() and not pyright_config.is_symlink() and not based_config.exists():
        surfaces.append(_json_strict_surface("Pyright", pyright_config))
    elif (
        _command_surface(scan, "pyright")
        and not based_config.exists()
        and not pyright_config.exists()
    ):
        surfaces.append(_missing_strict_surface("Pyright", "pyrightconfig.json"))

    for path in sorted(root.glob("tsconfig*.json")):
        if path.is_file() and not path.is_symlink():
            surfaces.append(_text_strict_surface("TypeScript", path))

    mypy_paths = [root / "mypy.ini", root / ".mypy.ini", root / "setup.cfg"]
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and _text_contains(pyproject, "[tool.mypy]"):
        mypy_paths.append(pyproject)
    for path in mypy_paths:
        section = "[tool.mypy]" if path.name == "pyproject.toml" else "[mypy"
        if path.is_file() and not path.is_symlink() and _text_contains(path, section):
            surfaces.append(_text_strict_surface("mypy", path))
    if _command_surface(scan, "mypy") and not any(item["provider"] == "mypy" for item in surfaces):
        surfaces.append(_missing_strict_surface("mypy", "mypy configuration"))
    if _command_surface(scan, "tsc") and not any(
        item["provider"] == "TypeScript" for item in surfaces
    ):
        surfaces.append(_missing_strict_surface("TypeScript", "tsconfig*.json"))
    return surfaces


def _basedpyright_surface(config_path: Path, baseline_path: Path) -> dict[str, Any]:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return _blocked_surface("BasedPyright", config_path, str(error))
    config_payload = cast(dict[str, object], config) if isinstance(config, dict) else {}
    strict = config_payload.get("typeCheckingMode") == "strict"
    if not strict:
        return _blocked_surface("BasedPyright", config_path, "typeCheckingMode is not strict")
    baseline_exists = baseline_path.is_file() and not baseline_path.is_symlink()
    return {
        "provider": "BasedPyright",
        "score": 4 if baseline_exists else 3,
        "status": "validated" if baseline_exists else "discoverable",
        "message": (
            "strict mode and its occurrence baseline are visible"
            if baseline_exists
            else "strict mode is configured but its occurrence baseline is missing"
        ),
        "evidence": [
            {"path": str(STRICT_CONFIG_PATH), "detail": "typeCheckingMode=strict"},
            {
                "path": str(STRICT_BASELINE_PATH),
                "detail": "occurrence baseline is present"
                if baseline_exists
                else "occurrence baseline is missing",
            },
        ],
    }


def _json_strict_surface(provider: str, path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return _blocked_surface(provider, path, str(error))
    payload_map = cast(dict[str, object], payload) if isinstance(payload, dict) else {}
    strict = payload_map.get("typeCheckingMode") == "strict"
    return _configured_surface(provider, path, strict)


def _text_strict_surface(provider: str, path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return _blocked_surface(provider, path, str(error))
    return _configured_surface(provider, path, bool(_STRICT_TRUE.search(text)))


def _configured_surface(provider: str, path: Path, strict: bool) -> dict[str, Any]:
    return {
        "provider": provider,
        "score": 3 if strict else 1,
        "status": "validated" if strict else "absent",
        "message": (
            "strict mode is configured"
            if strict
            else "a type configuration exists without strict mode"
        ),
        "evidence": [
            {
                "path": path.name,
                "detail": "strict mode is enabled" if strict else "strict mode is not enabled",
            }
        ],
    }


def _missing_strict_surface(provider: str, path: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "score": 1,
        "status": "absent",
        "message": "type checking is present but no strict config exposes its policy",
        "evidence": [{"path": path, "detail": "strict configuration is missing"}],
    }


def _blocked_surface(provider: str, path: Path, detail: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "score": 0,
        "status": "blocked",
        "message": "strict policy configuration could not be read",
        "evidence": [{"path": str(path), "detail": detail}],
    }


def _command_surface(scan: dict[str, Any], command_name: str) -> bool:
    commands = scan.get("quality_commands")
    if not isinstance(commands, list):
        return False
    for raw_item in cast(list[object], commands):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, object], raw_item)
        command = str(item.get("command", "")).lower()
        if command_name == "pyright" and "basedpyright" in command:
            continue
        if command_name in command:
            return True
    return False


def _text_contains(path: Path, value: str) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        return value.lower() in path.read_text(encoding="utf-8").lower()
    except OSError:
        return False


def assess_strict_type_debt(root: Path) -> dict[str, Any]:
    """Assess tracked strict debt without executing a repository command."""

    config_path = root / STRICT_CONFIG_PATH
    baseline_path = root / STRICT_BASELINE_PATH
    config_exists = config_path.is_file() and not config_path.is_symlink()
    baseline_exists = baseline_path.is_file() and not baseline_path.is_symlink()
    if not config_exists and not baseline_exists:
        return {
            "score": None,
            "status": "not_applicable",
            "message": "No repository-owned strict BasedPyright policy was found.",
            "evidence": [
                {"path": ".", "detail": "Neither the strict config nor its baseline exists."}
            ],
        }
    if not config_exists or not baseline_exists:
        missing = STRICT_CONFIG_PATH if not config_exists else STRICT_BASELINE_PATH
        return {
            "score": 0,
            "status": "blocked",
            "message": (
                "Strict BasedPyright policy is incomplete; its config and baseline "
                "must travel together."
            ),
            "evidence": [
                {"path": str(missing), "detail": "Required strict policy surface is missing."}
            ],
        }

    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return _blocked("Strict BasedPyright baseline is unreadable.", baseline_path, str(error))
    if not isinstance(baseline, dict):
        return _blocked(
            "Strict BasedPyright baseline is not a JSON object.",
            baseline_path,
            "invalid JSON shape",
        )

    baseline_map = cast(dict[str, object], baseline)
    legacy = baseline_map.get("legacy")
    coverage = baseline_map.get("coverage")
    legacy_map = cast(dict[str, object], legacy) if isinstance(legacy, dict) else {}
    occurrences = legacy_map.get("occurrences")
    if (
        baseline_map.get("schema") != STRICT_BASELINE_SCHEMA
        or baseline_map.get("tool") != "basedpyright"
        or not isinstance(occurrences, int)
        or isinstance(occurrences, bool)
        or occurrences < 0
        or not isinstance(coverage, dict)
        or cast(dict[str, object], coverage).get("state") != "complete"
    ):
        return _blocked(
            "Strict BasedPyright baseline is invalid or incomplete.",
            baseline_path,
            "schema, tool, occurrence count, or coverage contract failed",
        )

    score = _score_for_occurrences(occurrences)
    state = "clear" if occurrences == 0 else "tracked"
    baseline_ref = baseline_map.get("baseline_ref") or "unknown"
    return {
        "score": score,
        "status": "validated" if occurrences == 0 else "tracked",
        "message": (
            "Strict BasedPyright has no legacy diagnostics."
            if occurrences == 0
            else f"{occurrences:,} legacy strict diagnostics remain; the "
            "occurrence-aware ratchet keeps them explicitly blocked."
        ),
        "evidence": [
            {"path": str(STRICT_CONFIG_PATH), "detail": "strict typeCheckingMode is configured"},
            {
                "path": str(STRICT_BASELINE_PATH),
                "detail": f"state={state}; occurrences={occurrences}; baseline_ref={baseline_ref}",
            },
        ],
    }


def _blocked(message: str, path: Path, detail: str) -> dict[str, Any]:
    return {
        "score": 0,
        "status": "blocked",
        "message": message,
        "evidence": [{"path": str(path), "detail": detail}],
    }


def _score_for_occurrences(occurrences: int) -> int:
    """Map debt to the shared 0-4 maturity scale using explicit bands."""

    if occurrences == 0:
        return 4
    if occurrences <= 10:
        return 3
    if occurrences <= 100:
        return 2
    if occurrences <= 1000:
        return 1
    return 0
