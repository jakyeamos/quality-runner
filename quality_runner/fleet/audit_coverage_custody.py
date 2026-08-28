from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

CUSTODY_DISPOSITION_SCHEMA = "quality-runner-audit-custody-dispositions/v1"
ALLOWED_CUSTODY_DISPOSITIONS = frozenset(
    {
        "folded_into_target",
        "semantic_superseded",
        "pruned_stale_ref",
        "protected_canonical_line",
        "external_remote_line",
        "retained_active_lane",
        "retained_dirty_state",
    }
)


def load_custody_dispositions(path: Path | None) -> dict[str, list[dict[str, Any]]]:
    """Load exact, human-reviewable dispositions for live custody gaps.

    The manifest is evidence, not authority: each entry is matched against a
    live ref, checkout, head, or status hash during coverage assessment. An
    entry that does not match current state cannot make coverage complete.
    """

    if path is None:
        return {}
    payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"unsupported custody disposition schema: {path}")
    payload = cast(dict[str, Any], payload)
    if payload.get("schema") != CUSTODY_DISPOSITION_SCHEMA:
        raise ValueError(f"unsupported custody disposition schema: {path}")
    raw_repositories_value = payload.get("repositories")
    if not isinstance(raw_repositories_value, dict):
        raise ValueError("custody disposition manifest repositories must be an object")
    raw_repositories = cast(dict[str, Any], raw_repositories_value)
    result: dict[str, list[dict[str, Any]]] = {}
    for raw_path, raw_items_value in raw_repositories.items():
        if not raw_path:
            raise ValueError("custody disposition repository paths must be non-empty strings")
        if not isinstance(raw_items_value, list):
            raise ValueError(f"custody dispositions for {raw_path} must be an array of objects")
        raw_items = cast(list[object], raw_items_value)
        if not all(isinstance(item, dict) for item in raw_items):
            raise ValueError(f"custody dispositions for {raw_path} must be an array of objects")
        result[str(Path(raw_path).expanduser().resolve())] = [
            cast(dict[str, Any], item) for item in raw_items
        ]
    return result


def apply_custody_dispositions(
    *,
    target_head: str | None,
    unfolded: list[dict[str, Any]],
    dirty_worktrees: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
    supplied: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Apply only dispositions that match current live gap identity exactly."""

    gaps = [*unfolded, *dirty_worktrees, *ambiguous]
    dispositioned: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    used: set[int] = set()
    for gap in gaps:
        matches = [
            (index, item)
            for index, item in enumerate(supplied)
            if index not in used and _disposition_matches(gap, item, target_head=target_head)
        ]
        if not matches:
            continue
        if len(matches) > 1:
            errors.append(
                {
                    "kind": "custody_disposition",
                    "reason": "multiple dispositions match one live custody gap",
                    "gap": _gap_identity(gap),
                    "safe_action": "remove_duplicate_dispositions",
                }
            )
            continue
        index, item = matches[0]
        used.add(index)
        disposition = str(item.get("disposition", ""))
        reason = str(item.get("reason", "")).strip()
        evidence = item.get("evidence")
        if disposition not in ALLOWED_CUSTODY_DISPOSITIONS:
            errors.append(
                {
                    "kind": "custody_disposition",
                    "reason": f"unsupported custody disposition: {disposition or '<missing>'}",
                    "gap": _gap_identity(gap),
                    "safe_action": "use_a_supported_disposition",
                }
            )
            continue
        if not reason or evidence in (None, "", [], {}):
            errors.append(
                {
                    "kind": "custody_disposition",
                    "reason": "disposition requires a non-empty reason and evidence",
                    "gap": _gap_identity(gap),
                    "safe_action": "complete_disposition_evidence",
                }
            )
            continue
        dispositioned.append(
            {
                **gap,
                "disposition": "custody_dispositioned",
                "custody_disposition": {
                    "type": disposition,
                    "reason": reason,
                    "evidence": evidence,
                    "reviewed_at": item.get("reviewed_at"),
                },
            }
        )
    for index, item in enumerate(supplied):
        if index not in used:
            errors.append(
                {
                    "kind": "custody_disposition",
                    "reason": "disposition does not match a live custody gap",
                    "entry": _manifest_identity(item),
                    "safe_action": "refresh_the_manifest_against_live_state",
                }
            )
    dispositioned_keys = {_gap_key(item) for item in dispositioned}
    return (
        [item for item in unfolded if _gap_key(item) not in dispositioned_keys],
        [item for item in dirty_worktrees if _gap_key(item) not in dispositioned_keys],
        [item for item in ambiguous if _gap_key(item) not in dispositioned_keys],
        dispositioned,
        errors,
    )


def _disposition_matches(
    gap: dict[str, Any], item: dict[str, Any], *, target_head: str | None
) -> bool:
    if target_head and item.get("target_head") not in (None, target_head):
        return False
    kind = item.get("kind")
    if kind not in (None, gap.get("kind")):
        return False
    if item.get("ref") not in (None, gap.get("ref"), *(gap.get("aliases") or [])):
        return False
    if item.get("head") not in (None, gap.get("head")):
        return False
    if item.get("checkout_id") not in (None, gap.get("checkout_id")):
        return False
    if item.get("status_hash") not in (None, gap.get("status_hash")):
        return False
    return any(item.get(key) is not None for key in ("ref", "head", "checkout_id", "status_hash"))


def _gap_key(item: Mapping[str, Any]) -> tuple[object, ...]:
    return (
        item.get("kind"),
        item.get("ref"),
        item.get("head"),
        item.get("checkout_id"),
        item.get("status_hash"),
    )


def _gap_identity(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("kind", "ref", "head", "checkout_id", "status_hash")
        if item.get(key) is not None
    }


def _manifest_identity(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("kind", "ref", "head", "checkout_id", "status_hash", "disposition")
        if item.get(key) is not None
    }
