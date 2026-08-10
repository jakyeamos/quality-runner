from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, cast

from quality_runner.maintenance_surface_diff import Comparison, git_output

REGRESSION_PROOF_SCHEMA = "quality-runner-regression-proof-v0.1"
MAX_REMOVAL_CANDIDATES = 50
MAX_RESIDUAL_REFERENCES = 20

_REMOVED_DECLARATION = re.compile(
    r"^(?:export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type|enum)\s+"
    r"|(?:async\s+)?def\s+|class\s+|pub\s+(?:async\s+)?(?:fn|struct|enum|trait|type|const)\s+"
    r"|(?:func|type|const|var)\s+)([A-Za-z_][A-Za-z0-9_]*)"
)


def contract_evidence(
    config: dict[str, Any],
    changes: list[dict[str, Any]],
    candidates: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    raw_section: object = config.get("maintenance_surface")
    section = cast(dict[str, object], raw_section) if isinstance(raw_section, dict) else None
    relevant_warnings = [
        item
        for item in config.get("warnings", [])
        if "quality_runner.maintenance_surface" in str(item.get("message", ""))
    ]
    if section is None or not section.get("enabled"):
        return {
            "status": "invalid" if relevant_warnings else "not_configured",
            "behavior_owners": [],
            "compatibility": [],
            "observations": [],
            "invalid_config": bool(relevant_warnings),
        }
    owners = _contract_list(section.get("behavior_owners"))
    compatibility = _contract_list(section.get("compatibility"))
    changed_paths = [item["path"] for item in changes]
    observations: list[dict[str, Any]] = []
    for candidate in candidates["public_surfaces"]:
        matches = [item for item in owners if _matches_any(candidate["path"], item["paths"])]
        if len(matches) != 1:
            observations.append(
                observation(
                    "public-surface-owner",
                    "A public-surface candidate does not map to exactly one declared behavior owner.",
                    evidence=[candidate["path"], f"matching_owners={len(matches)}"],
                )
            )
    for candidate in candidates["compatibility"]:
        matches = [item for item in compatibility if _matches_any(candidate["path"], item["paths"])]
        if len(matches) != 1:
            observations.append(
                observation(
                    "compatibility-contract",
                    "A compatibility candidate does not map to exactly one declared compatibility contract.",
                    evidence=[candidate["path"], f"matching_contracts={len(matches)}"],
                )
            )
    return {
        "status": "invalid" if relevant_warnings else "configured",
        "behavior_owners": [
            item | {"changed_paths": _matching_paths(changed_paths, item["paths"])}
            for item in owners
        ],
        "compatibility": [
            item | {"changed_paths": _matching_paths(changed_paths, item["paths"])}
            for item in compatibility
        ],
        "observations": observations,
        "invalid_config": bool(relevant_warnings),
    }


def regression_proof(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"schema": REGRESSION_PROOF_SCHEMA, "status": "not_provided"}
    source = path.expanduser().resolve()
    try:
        raw_payload: object = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "schema": REGRESSION_PROOF_SCHEMA,
            "status": "invalid",
            "reason": str(error),
            "source": str(source),
        }
    if not isinstance(raw_payload, dict):
        return _invalid_proof(source, "proof must be a JSON object")
    payload = cast(dict[str, object], raw_payload)
    if payload.get("schema") != REGRESSION_PROOF_SCHEMA:
        return _invalid_proof(source, "schema must be quality-runner-regression-proof-v0.1")
    status = payload.get("status")
    if status == "unavailable":
        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason:
            return _invalid_proof(source, "unavailable proof requires a non-empty reason")
        return payload | {"source": str(source)}
    required = {
        "test": str,
        "defective_revision": str,
        "fixed_revision": str,
    }
    if status != "verified" or any(
        not isinstance(payload.get(field), expected) or not payload[field]
        for field, expected in required.items()
    ):
        return _invalid_proof(source, "verified proof requires test and both revision identifiers")
    if payload.get("defective_result") != "failed" or payload.get("fixed_result") != "passed":
        return _invalid_proof(source, "verified proof requires defective=failed and fixed=passed")
    return payload | {"source": str(source)}


def vertical_slice_review(
    root: Path,
    comparison: Comparison,
    changes: list[dict[str, Any]],
    patch: str,
) -> list[dict[str, Any]]:
    candidates: list[tuple[str, str]] = []
    current_path = ""
    for line in patch.splitlines():
        if line.startswith("--- a/"):
            current_path = line[6:]
            continue
        if line.startswith("-") and not line.startswith("---"):
            match = _REMOVED_DECLARATION.match(line[1:].strip())
            if match:
                candidates.append((match.group(1), current_path))
    for item in changes:
        if item["status"] == "deleted":
            candidates.append((PurePosixPath(item["path"]).stem, item["path"]))

    observations: list[dict[str, Any]] = []
    for symbol, removed_path in list(dict.fromkeys(candidates))[:MAX_REMOVAL_CANDIDATES]:
        if len(symbol) < 4:
            continue
        references = _remaining_references(root, comparison, symbol, removed_path)
        if references:
            observations.append(
                observation(
                    "vertical-slice-removal",
                    f"Removed candidate '{symbol}' still has repository references to review.",
                    evidence=[removed_path, *references],
                    confidence="medium",
                )
            )
    return observations


def observation(
    observation_id: str,
    message: str,
    *,
    evidence: list[str],
    confidence: str = "low",
) -> dict[str, Any]:
    return {
        "id": observation_id,
        "severity": "observation",
        "confidence": confidence,
        "review_required": True,
        "message": message,
        "evidence": evidence,
    }


def _remaining_references(
    root: Path, comparison: Comparison, symbol: str, removed_path: str
) -> list[str]:
    if comparison.working_tree:
        try:
            output = git_output(
                root,
                "grep",
                "-n",
                "-I",
                "-F",
                symbol,
                "--",
                ":(exclude).git",
                allow_no_match=True,
            )
        except ValueError:
            return []
    else:
        output = git_output(
            root,
            "grep",
            "-n",
            "-I",
            "-F",
            symbol,
            comparison.head_commit,
            "--",
            allow_no_match=True,
        )
    return [line[:300] for line in output.splitlines() if removed_path not in line][
        :MAX_RESIDUAL_REFERENCES
    ]


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _matching_paths(paths: list[str], patterns: list[str]) -> list[str]:
    return [path for path in paths if _matches_any(path, patterns)]


def _contract_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        cast(dict[str, Any], item) for item in cast(list[object], value) if isinstance(item, dict)
    ]


def _invalid_proof(source: Path, reason: str) -> dict[str, Any]:
    return {
        "schema": REGRESSION_PROOF_SCHEMA,
        "status": "invalid",
        "reason": reason,
        "source": str(source),
    }
