from __future__ import annotations

from typing import Any

from quality_runner.schema_constants import CONTROLLER_REPORT_VALIDATION_SCHEMA

CONTROLLER_REPORT_LINT_SCHEMA = "quality-runner-controller-report-lint-v0.1"
CONTROLLER_REPORT_SCHEMA = "quality-runner-controller-report-v0.1"
TERMINAL_STATUSES = {"ready-for-review", "blocked", "complete"}


def validate_controller_report(report: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    status = report.get("status")
    if status not in TERMINAL_STATUSES:
        errors.append("report status must be ready-for-review, blocked, or complete")

    for field in ("repo_path", "branch_name", "baseline_artifact_path"):
        if not _non_empty_string(report.get(field)):
            errors.append(f"{field} must be a non-empty string")

    if not isinstance(report.get("final_qr"), dict):
        errors.append("final_qr must be an object")
    if not isinstance(report.get("files_changed"), list):
        errors.append("files_changed must be a list")
    if not isinstance(report.get("verification"), list):
        errors.append("verification must be a list")
    if not isinstance(report.get("blockers"), list):
        errors.append("blockers must be a list")
    ignored_generated_artifacts = report.get("ignored_generated_artifacts")
    if ignored_generated_artifacts is not None and not _string_list(ignored_generated_artifacts):
        errors.append("ignored_generated_artifacts must be a list of non-empty strings")

    git_status = report.get("git_status_short")
    if not isinstance(git_status, str):
        errors.append("git_status_short must be a string")
    elif (
        status in {"complete", "ready-for-review"}
        and git_status.strip()
        and not _only_ignored_generated_artifacts(git_status, ignored_generated_artifacts)
    ):
        errors.append("completed reports must have a clean git_status_short field")

    if status == "complete":
        if not _non_empty_string(report.get("commit_hash")):
            errors.append("completed reports must include a commit_hash")
        if report.get("push_status") != "pushed":
            errors.append('completed reports must have push_status "pushed"')
    elif status == "blocked":
        blockers = report.get("blockers")
        if isinstance(blockers, list) and not blockers:
            errors.append("blocked reports must include at least one blocker")

    return {
        "schema": CONTROLLER_REPORT_VALIDATION_SCHEMA,
        "status": "rejected" if errors else "accepted",
        "errors": errors,
    }


def normalize_controller_report(report: dict[str, Any]) -> dict[str, Any]:
    final_qr = _normalized_final_qr(report)
    blockers = _normalized_blockers(report.get("blockers"))
    status = _normalized_status(report=report, final_qr=final_qr, blockers=blockers)
    repo_path = _first_string(
        report.get("repo_path"),
        _nested(report, "target", "repo_path"),
        _nested(report, "target", "repo"),
        _nested(report, "run", "target_repo"),
    )
    return {
        "schema": CONTROLLER_REPORT_SCHEMA,
        "repo_path": repo_path,
        "branch_name": _first_string(
            report.get("branch_name"),
            _nested(report, "target", "branch"),
            _nested(report, "target", "git_branch"),
            _nested(report, "run", "target_branch"),
            _nested(report, "run", "branch"),
            _nested(report, "controller_context", "branch"),
            _nested(report, "controller", "branch"),
            report.get("branch_context"),
            _nested(report, "run", "controller_branch"),
        ),
        "status": status,
        "baseline_artifact_path": _normalized_baseline_artifact_path(report, repo_path),
        "final_qr": final_qr,
        "files_changed": _normalized_files_changed(report.get("files_changed")),
        "verification": _normalized_verification(report),
        "commit_hash": _normalized_commit_hash(report),
        "push_status": _normalized_push_status(report),
        "git_status_short": _normalized_git_status_short(report),
        "ignored_generated_artifacts": _normalized_ignored_generated_artifacts(report),
        "blockers": blockers if status == "blocked" or blockers else _inferred_blockers(final_qr),
    }


def lint_controller_report(report: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    normalized = normalize_controller_report(report)
    validation = validate_controller_report(normalized)
    errors = list(validation["errors"])
    if strict:
        errors.extend(_strict_errors(raw=report, normalized=normalized))
    return {
        "schema": CONTROLLER_REPORT_LINT_SCHEMA,
        "status": "rejected" if errors else "accepted",
        "errors": errors,
        "normalized_report": normalized,
    }


def build_controller_report_from_summary(
    *,
    repo_path: str,
    branch_name: str,
    summary: dict[str, Any],
    baseline_run_id: str | None,
    git_status_short: str,
    files_changed: list[str] | None = None,
    verification: list[dict[str, str]] | None = None,
    blockers: list[str] | None = None,
    commit_hash: str | None = None,
    push_status: str = "not-pushed",
    ignored_generated_artifacts: list[str] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    final_qr = {
        "run_id": summary.get("run_id"),
        "status": summary.get("status"),
        "classification": summary.get("recommended_classification"),
        "artifact_path": summary.get("path"),
        "gate_verification_status": summary.get("gate_verification_status"),
        "audit_status": summary.get("audit_status"),
        "findings_total": _nested(summary, "finding_counts", "total"),
        "missing_capabilities": summary.get("missing_capabilities", []),
    }
    normalized_blockers = blockers if blockers is not None else _inferred_blockers(final_qr)
    resolved_status = status or _status_from_summary(final_qr, commit_hash=commit_hash, push_status=push_status)
    return {
        "schema": CONTROLLER_REPORT_SCHEMA,
        "repo_path": repo_path,
        "branch_name": branch_name,
        "status": resolved_status,
        "baseline_artifact_path": _baseline_path(repo_path=repo_path, baseline_run_id=baseline_run_id)
        or str(summary.get("path") or ""),
        "final_qr": {key: value for key, value in final_qr.items() if value is not None},
        "files_changed": files_changed or [],
        "verification": verification
        or [
            {
                "command": f"quality-runner summarize-run {repo_path} --run-id {summary.get('run_id')}",
                "result": str(summary.get("status") or "unknown"),
            }
        ],
        "commit_hash": commit_hash,
        "push_status": push_status,
        "git_status_short": git_status_short,
        "ignored_generated_artifacts": ignored_generated_artifacts
        or _default_ignored_generated_artifacts(git_status_short),
        "blockers": normalized_blockers if resolved_status == "blocked" else blockers or [],
    }


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _only_ignored_generated_artifacts(git_status: str, ignored: object) -> bool:
    if not _string_list(ignored):
        return False
    ignored_paths = [item.rstrip("/") for item in ignored]
    lines = [line for line in git_status.splitlines() if line.strip()]
    if not lines:
        return True
    return all(_line_is_ignored(line, ignored_paths) for line in lines)


def _line_is_ignored(line: str, ignored_paths: list[str]) -> bool:
    path = line[3:].strip() if len(line) > 3 else line.strip()
    normalized = path.rstrip("/")
    return any(normalized == ignored or normalized.startswith(f"{ignored}/") for ignored in ignored_paths)


def _normalized_final_qr(report: dict[str, Any]) -> dict[str, Any]:
    final_qr = report.get("final_qr")
    if isinstance(final_qr, dict):
        return dict(final_qr)
    for value in (
        report.get("final_quality_runner_status"),
        _nested(report, "quality_runner_result", "summary"),
        report.get("quality_runner_result"),
        report.get("refresh_result"),
        report.get("refresh"),
    ):
        if isinstance(value, dict):
            return _compact(
                {
                    "run_id": _first_string(
                        value.get("run_id"),
                        value.get("final_run_id"),
                        _nested(report, "quality_runner_result", "final_run_id"),
                    ),
                    "status": _first_string(
                        value.get("status"),
                        value.get("final_status"),
                        _nested(report, "quality_runner_result", "final_status"),
                    ),
                    "classification": _first_string(
                        value.get("classification"),
                        value.get("recommended_classification"),
                        _nested(report, "quality_runner_result", "final_classification"),
                    ),
                    "gate_verification_status": value.get("gate_verification_status"),
                    "audit_status": value.get("audit_status"),
                    "findings_total": _first_value(
                        value.get("findings_total"),
                        _nested(value, "finding_counts", "total"),
                        _nested(report, "quality_runner_result", "summary", "final_findings_total"),
                    ),
                    "missing_capabilities": value.get("missing_capabilities", []),
                }
            )
    return {}


def _normalized_status(
    *,
    report: dict[str, Any],
    final_qr: dict[str, Any],
    blockers: list[str],
) -> str:
    raw_status = report.get("status")
    final_status = str(final_qr.get("status") or "")
    if raw_status in {"blocked", "ready-for-review"}:
        return str(raw_status)
    if raw_status == "complete":
        if _final_qr_clean(final_qr) and _normalized_push_status(report) == "pushed":
            return "complete"
        if blockers or final_status in {"blocked", "failed"}:
            return "blocked"
        return "ready-for-review"
    if blockers or final_status in {"blocked", "failed"}:
        return "blocked"
    if _final_qr_clean(final_qr):
        return "ready-for-review"
    return "blocked" if final_qr else ""


def _normalized_baseline_artifact_path(report: dict[str, Any], repo_path: str) -> str:
    direct = _first_string(
        report.get("baseline_artifact_path"),
        _nested(report, "baseline", "artifact_path"),
    )
    if direct:
        return direct
    baseline_run_id = _first_string(
        _nested(report, "baseline", "used_run_id"),
        _nested(report, "baseline", "requested_run_id"),
        _nested(report, "target", "baseline_run_id"),
        _nested(report, "run", "baseline_run_id_requested"),
    )
    return _baseline_path(repo_path=repo_path, baseline_run_id=baseline_run_id) or ""


def _baseline_path(*, repo_path: str, baseline_run_id: str | None) -> str | None:
    if not repo_path or not baseline_run_id:
        return None
    return f"{repo_path.rstrip('/')}/.quality-runner/runs/{baseline_run_id}"


def _normalized_files_changed(value: object) -> list[str]:
    if _string_list(value):
        return list(value)
    if not isinstance(value, dict):
        return []
    for key in ("tracked", "tracked_repo_files", "by_this_task", "tracked_repo_files_modified_after_run"):
        nested = value.get(key)
        if _string_list(nested):
            return list(nested)
    return []


def _normalized_verification(report: dict[str, Any]) -> list[dict[str, str]]:
    verification = report.get("verification")
    if isinstance(verification, list):
        normalized = [
            {
                "command": str(item.get("command")),
                "result": str(item.get("result")),
            }
            for item in verification
            if isinstance(item, dict) and item.get("command") is not None and item.get("result") is not None
        ]
        if normalized:
            return normalized
    argv = _nested(report, "command", "argv")
    if isinstance(argv, list) and argv:
        return [{"command": " ".join(str(part) for part in argv), "result": str(_nested(report, "command", "exit_code"))}]
    command = _nested(report, "run", "command")
    if isinstance(command, str) and command:
        return [{"command": command, "result": str(_nested(report, "run", "exit_code"))}]
    return []


def _normalized_commit_hash(report: dict[str, Any]) -> str | None:
    value = _first_string(
        report.get("commit_hash"),
        _nested(report, "commit_push", "commit_hash"),
        _nested(report, "commit_push", "commit"),
    )
    if value in {"not_performed", "not-created", "not created"}:
        return None
    return value or None


def _normalized_push_status(report: dict[str, Any]) -> str:
    value = report.get("push_status")
    if isinstance(value, str) and value:
        return value
    for path in (("commit_push", "push"), ("commit_push", "push_status")):
        nested = _nested(report, *path)
        if isinstance(nested, str) and nested:
            return "not-pushed" if nested == "not_performed" else nested
    for path in (("commit_push", "pushed"), ("commit_push", "push_performed")):
        nested = _nested(report, *path)
        if isinstance(nested, bool):
            return "pushed" if nested else "not-pushed"
    return "not-pushed"


def _normalized_git_status_short(report: dict[str, Any]) -> str:
    for value in (
        report.get("git_status_short"),
        _nested(report, "target", "git_status_short"),
        _nested(report, "git_status", "after", "all_short"),
    ):
        if isinstance(value, str):
            return value
    for value in (_nested(report, "target", "final_git_status"), _nested(report, "target", "post_status")):
        if isinstance(value, list):
            return "\n".join(str(item) for item in value if _looks_like_git_status_line(item))
    return ""


def _normalized_ignored_generated_artifacts(report: dict[str, Any]) -> list[str]:
    ignored = report.get("ignored_generated_artifacts")
    if _string_list(ignored):
        return list(ignored)
    git_status = _normalized_git_status_short(report)
    return _default_ignored_generated_artifacts(git_status)


def _default_ignored_generated_artifacts(git_status: str) -> list[str]:
    return [".quality-runner/"] if ".quality-runner/" in git_status else []


def _normalized_blockers(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    blockers: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            blockers.append(item)
        elif isinstance(item, dict):
            detail = _first_string(item.get("detail"), item.get("summary"), item.get("id"), item.get("class"))
            if detail:
                blockers.append(detail)
    return blockers


def _inferred_blockers(final_qr: dict[str, Any]) -> list[str]:
    classification = _first_string(final_qr.get("classification"), final_qr.get("recommended_classification"))
    status = _first_string(final_qr.get("status"))
    if classification and classification != "clean":
        return [classification]
    if status and not _final_qr_clean(final_qr):
        return [status]
    return []


def _strict_errors(*, raw: dict[str, Any], normalized: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if raw.get("status") == "complete" and not _final_qr_clean(normalized.get("final_qr", {})):
        errors.append("complete reports must have final_qr status clean/passed")
    if _head_changed_without_note(raw):
        errors.append("reports with target HEAD changes must include an explicit concurrency note")
    return errors


def _head_changed_without_note(report: dict[str, Any]) -> bool:
    observed = _nested(report, "target", "concurrent_head_change_observed")
    if isinstance(observed, dict):
        if observed.get("observed") is not True:
            return False
        return not _first_string(observed.get("note"), observed.get("detail"), observed.get("reason"))
    repo_state = report.get("repo_state")
    if not isinstance(repo_state, dict):
        return False
    before = _first_string(repo_state.get("pre_head"), repo_state.get("before_head"))
    after = _first_string(repo_state.get("post_head"), repo_state.get("after_head"))
    if not before or not after or before == after:
        return False
    return not _first_string(repo_state.get("concurrency_note"), repo_state.get("note"))


def _status_from_summary(
    final_qr: dict[str, Any],
    *,
    commit_hash: str | None,
    push_status: str,
) -> str:
    if _final_qr_clean(final_qr):
        return "complete" if commit_hash and push_status == "pushed" else "ready-for-review"
    return "blocked"


def _final_qr_clean(final_qr: object) -> bool:
    if not isinstance(final_qr, dict):
        return False
    status = str(final_qr.get("status") or "")
    classification = str(final_qr.get("classification") or final_qr.get("recommended_classification") or "")
    return status in {"clean", "passed"} or classification == "clean"


def _looks_like_git_status_line(value: object) -> bool:
    return isinstance(value, str) and len(value) >= 3 and value[:2].strip() in {"M", "A", "D", "R", "C", "U", "??"}


def _nested(payload: dict[str, Any], *keys: str) -> object:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_string(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


def _first_value(*values: object) -> object:
    for value in values:
        if value is not None:
            return value
    return None


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "", [])}
