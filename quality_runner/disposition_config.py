from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, TypeGuard

CONFIG_FILE_NAME = ".quality-runner.toml"
DISPOSITION_FILE_NAME = ".quality-runner-dispositions.toml"
DISPOSITION_SCHEMA = "quality-runner-dispositions-v1"
ACCEPTED_DISPOSITION_STATUSES = {
    "accepted-intentional",
    "accepted-false-positive",
    "blocked-with-prerequisite",
}


def parse_inline_dispositions(
    value: object,
    warnings: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(
            _warning(
                "invalid_quality_runner_config_field",
                "quality_runner.accepted_dispositions must be a list of tables",
            )
        )
        return []

    accepted: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            _inline_disposition_warning(index, warnings)
            continue
        fingerprint = item.get("fingerprint")
        status = item.get("status")
        reason = item.get("reason")
        owner = item.get("owner")
        expires = item.get("expires")
        source_run_id = item.get("source_run_id")
        review_evidence = item.get("review_evidence")
        if _valid_disposition_fields(
            fingerprint,
            status,
            reason,
            owner,
            expires,
            source_run_id,
            review_evidence,
        ):
            accepted.append(
                {
                    "fingerprint": fingerprint,
                    "status": status,
                    "reason": reason,
                    "owner": owner,
                    **({"expires": expires} if isinstance(expires, str) and expires else {}),
                    **(
                        {"source_run_id": source_run_id}
                        if isinstance(source_run_id, str) and source_run_id
                        else {}
                    ),
                    **(
                        {"review_evidence": review_evidence}
                        if isinstance(review_evidence, list) and review_evidence
                        else {}
                    ),
                }
            )
        else:
            _inline_disposition_warning(index, warnings)
    return accepted


def load_grouped_dispositions(
    repo_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    path = repo_root / DISPOSITION_FILE_NAME
    if not path.exists():
        return [], []
    warnings: list[dict[str, str]] = []
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        return [], [
            _warning(
                "invalid_quality_runner_dispositions",
                f"{DISPOSITION_FILE_NAME} could not be parsed as TOML: {error}",
                path=DISPOSITION_FILE_NAME,
            )
        ]
    section = payload.get("quality_runner")
    groups = section.get("accepted_disposition_groups") if isinstance(section, dict) else None
    if not isinstance(groups, list):
        return [], [
            _warning(
                "invalid_quality_runner_dispositions",
                f"{DISPOSITION_FILE_NAME} must define quality_runner.accepted_disposition_groups as a list of tables",
                path=DISPOSITION_FILE_NAME,
            )
        ]
    schema = payload.get("schema")
    if schema is None and isinstance(section, dict):
        schema = section.get("schema")
    if schema != DISPOSITION_SCHEMA:
        warnings.append(
            _warning(
                "invalid_quality_runner_dispositions",
                f"{DISPOSITION_FILE_NAME} must declare schema {DISPOSITION_SCHEMA}",
                path=DISPOSITION_FILE_NAME,
            )
        )
    accepted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            _group_disposition_warning(index, warnings)
            continue
        fingerprints = group.get("fingerprints")
        if not _valid_fingerprint_list(fingerprints) or any(item in seen for item in fingerprints):
            _group_disposition_warning(index, warnings)
            continue
        status = group.get("status")
        reason = group.get("reason")
        owner = group.get("owner")
        expires = group.get("expires")
        source_run_id = group.get("source_run_id")
        review_evidence = group.get("review_evidence")
        if not _valid_disposition_fields(
            None,
            status,
            reason,
            owner,
            expires,
            source_run_id,
            review_evidence,
        ):
            _group_disposition_warning(index, warnings)
            continue
        seen.update(fingerprints)
        for fingerprint in fingerprints:
            accepted.append(
                {
                    "fingerprint": fingerprint,
                    "status": status,
                    "reason": reason,
                    "owner": owner,
                    **({"expires": expires} if isinstance(expires, str) and expires else {}),
                    **(
                        {"source_run_id": source_run_id}
                        if isinstance(source_run_id, str) and source_run_id
                        else {}
                    ),
                    **(
                        {"review_evidence": review_evidence}
                        if isinstance(review_evidence, list) and review_evidence
                        else {}
                    ),
                }
            )
    return accepted, warnings


def _valid_fingerprint_list(value: object) -> TypeGuard[list[str]]:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item for item in value)
    )


def _valid_disposition_fields(
    fingerprint: object,
    status: object,
    reason: object,
    owner: object,
    expires: object,
    source_run_id: object,
    review_evidence: object,
) -> bool:
    return (
        (fingerprint is None or (isinstance(fingerprint, str) and bool(fingerprint)))
        and isinstance(status, str)
        and status in ACCEPTED_DISPOSITION_STATUSES
        and isinstance(reason, str)
        and bool(reason)
        and isinstance(owner, str)
        and bool(owner)
        and (expires is None or isinstance(expires, str))
        and (source_run_id is None or isinstance(source_run_id, str))
        and (
            review_evidence is None
            or (
                isinstance(review_evidence, list)
                and all(isinstance(item, str) and item for item in review_evidence)
            )
        )
    )


def _inline_disposition_warning(index: int, warnings: list[dict[str, str]]) -> None:
    warnings.append(
        _warning(
            "invalid_quality_runner_config_field",
            f"quality_runner.accepted_dispositions[{index}] must include fingerprint, status, reason, owner, and optional expires strings",
        )
    )


def _group_disposition_warning(index: int, warnings: list[dict[str, str]]) -> None:
    warnings.append(
        _warning(
            "invalid_quality_runner_dispositions",
            f"{DISPOSITION_FILE_NAME}.accepted_disposition_groups[{index}] must include unique fingerprints and valid disposition fields",
            path=DISPOSITION_FILE_NAME,
        )
    )


def _warning(code: str, message: str, *, path: str = CONFIG_FILE_NAME) -> dict[str, str]:
    return {"code": code, "message": message, "path": path}
