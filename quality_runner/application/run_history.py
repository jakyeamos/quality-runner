from __future__ import annotations

from pathlib import Path
from typing import cast

from quality_runner.artifacts import artifact_run_ids, existing_artifact_dir, validate_run_id
from quality_runner.run_summary import build_run_summary

DEFAULT_HISTORY_LIMIT = 20
MAX_HISTORY_LIMIT = 100

type HistoryPayload = dict[str, object]


def load_run_history(
    *,
    repo_root: Path,
    limit: int = DEFAULT_HISTORY_LIMIT,
    run_id: str | None = None,
) -> HistoryPayload:
    _validate_limit(limit)
    if run_id is not None:
        validate_run_id(run_id)
        unavailable_selected_run_ids: list[str] = []
        try:
            runs = [_run_summary(repo_root, run_id)]
        except (FileNotFoundError, OSError, ValueError):
            runs = []
            unavailable_selected_run_ids = [run_id]
        return {
            "repo_root": str(repo_root),
            "runs": runs,
            "selected_run_id": run_id,
            "truncated": False,
            "unavailable_run_ids": unavailable_selected_run_ids,
        }

    run_ids = _newest_run_ids(repo_root)
    selected = run_ids[:limit]
    runs: list[HistoryPayload] = []
    unavailable_run_ids: list[str] = []
    for candidate in selected:
        try:
            runs.append(_run_summary(repo_root, candidate))
        except (FileNotFoundError, OSError, ValueError):
            unavailable_run_ids.append(candidate)
    return {
        "repo_root": str(repo_root),
        "runs": runs,
        "truncated": len(run_ids) > len(selected),
        "unavailable_run_ids": unavailable_run_ids,
    }


def _newest_run_ids(repo_root: Path) -> list[str]:
    candidates = [
        (run_id, existing_artifact_dir(repo_root, run_id)) for run_id in artifact_run_ids(repo_root)
    ]
    return [
        run_id
        for run_id, _path in sorted(
            candidates,
            key=lambda item: (item[1].stat().st_mtime_ns, item[0]),
            reverse=True,
        )
    ]


def _run_summary(repo_root: Path, run_id: str) -> HistoryPayload:
    return cast(
        HistoryPayload, build_run_summary(repo_root=repo_root, run_id=run_id, persist=False)
    )


def _validate_limit(limit: int) -> None:
    if limit < 1 or limit > MAX_HISTORY_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_HISTORY_LIMIT}")
