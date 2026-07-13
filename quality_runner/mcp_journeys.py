from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from quality_runner.application.journey_outcomes import (
    audit_journey_outcome,
    runs_journey_outcome,
    verify_journey_outcome,
)
from quality_runner.application.run_history import DEFAULT_HISTORY_LIMIT, MAX_HISTORY_LIMIT
from quality_runner.compatibility.review_mcp import (
    review_mcp_input_schema,
    review_mcp_journey_outcome,
)
from quality_runner.core.audit_contracts import AuditPayload
from quality_runner.core.outcome_contracts import JourneyOutcome
from quality_runner.intent import resolve_workflow_intent
from quality_runner.workflow_internal import generated_run_id

AUDIT_OUTCOME_TOOL = "quality_runner_audit_outcome"
REVIEW_OUTCOME_TOOL = "quality_runner_review_outcome"
VERIFY_OUTCOME_TOOL = "quality_runner_verify_outcome"
RUNS_OUTCOME_TOOL = "quality_runner_runs_outcome"

JOURNEY_TOOL_NAMES = frozenset(
    {
        AUDIT_OUTCOME_TOOL,
        REVIEW_OUTCOME_TOOL,
        VERIFY_OUTCOME_TOOL,
        RUNS_OUTCOME_TOOL,
    }
)

_AUDIT_ARGUMENTS = frozenset(
    {
        "repo_root",
        "run_id",
        "profile",
        "ci_status_json",
        "intent",
        "intent_file",
        "include_ignored_paths",
        "checkout_most_advanced_branch",
        "mode",
    }
)
_VERIFY_ARGUMENTS = frozenset(
    {
        "repo_root",
        "run_id",
        "profile",
        "ci_status_json",
        "intent",
        "intent_file",
        "timeout_seconds",
        "checkout_most_advanced_branch",
        "execute_gates",
        "read_only_gates",
        "allow_mutating_gates",
        "worktree_mode",
        "allow_dirty_worktree_verify",
    }
)
_RUNS_ARGUMENTS = frozenset({"repo_root", "run_id", "limit"})


def journey_tools() -> list[dict[str, object]]:
    return [
        {
            "name": AUDIT_OUTCOME_TOOL,
            "description": (
                "Inspect or audit a repository and return the concise Quality Runner outcome. "
                "It may write evidence artifacts but never edits source files."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo_root": {"type": "string"},
                    "run_id": {"type": "string"},
                    "profile": {"type": "string"},
                    "ci_status_json": {"type": "string"},
                    "intent": {"type": "string"},
                    "intent_file": {"type": "string"},
                    "include_ignored_paths": {"type": "array", "items": {"type": "string"}},
                    "checkout_most_advanced_branch": {"type": "boolean"},
                    "mode": {"type": "string", "enum": ["plan", "inspect"]},
                },
                "required": ["repo_root"],
                "additionalProperties": False,
            },
        },
        {
            "name": REVIEW_OUTCOME_TOOL,
            "description": (
                "Run a read-only review and return its Quality Runner outcome. "
                "A prepared packet is reported as awaiting independent evidence."
            ),
            "inputSchema": _review_input_schema(),
        },
        {
            "name": VERIFY_OUTCOME_TOOL,
            "description": (
                "Record or execute verification gates and return the Quality Runner outcome. "
                "Executing commands requires execute_gates with a disposable worktree."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo_root": {"type": "string"},
                    "run_id": {"type": "string"},
                    "profile": {"type": "string"},
                    "ci_status_json": {"type": "string"},
                    "intent": {"type": "string"},
                    "intent_file": {"type": "string"},
                    "timeout_seconds": {"type": "integer", "minimum": 1},
                    "checkout_most_advanced_branch": {"type": "boolean"},
                    "execute_gates": {"type": "boolean"},
                    "read_only_gates": {"type": "boolean"},
                    "allow_mutating_gates": {"type": "boolean"},
                    "worktree_mode": {
                        "type": "string",
                        "enum": ["in-place", "disposable"],
                    },
                    "allow_dirty_worktree_verify": {"type": "boolean"},
                },
                "required": ["repo_root"],
                "additionalProperties": False,
            },
        },
        {
            "name": RUNS_OUTCOME_TOOL,
            "description": "Read Quality Runner run history without writing new artifacts.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo_root": {"type": "string"},
                    "run_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_HISTORY_LIMIT},
                },
                "required": ["repo_root"],
                "additionalProperties": False,
            },
        },
    ]


def is_journey_tool(name: str) -> bool:
    return name in JOURNEY_TOOL_NAMES


def journey_tool_payload(
    name: str,
    arguments: Mapping[str, object],
    *,
    repo_root: Path,
) -> JourneyOutcome:
    if name == AUDIT_OUTCOME_TOOL:
        return _audit_outcome(arguments, repo_root=repo_root)
    if name == REVIEW_OUTCOME_TOOL:
        return _review_outcome(arguments, repo_root=repo_root)
    if name == VERIFY_OUTCOME_TOOL:
        return _verify_outcome(arguments, repo_root=repo_root)
    if name == RUNS_OUTCOME_TOOL:
        return _runs_outcome(arguments, repo_root=repo_root)
    raise ValueError(f"Unknown Quality Runner MCP journey tool: {name}")


def _audit_outcome(arguments: Mapping[str, object], *, repo_root: Path) -> JourneyOutcome:
    _reject_unknown_arguments(arguments, _AUDIT_ARGUMENTS)
    run_id = _optional_string(arguments, "run_id") or generated_run_id()
    return audit_journey_outcome(
        repo_root=repo_root,
        run_id=run_id,
        profile=_optional_string(arguments, "profile"),
        ci_status_json=_optional_path(arguments, "ci_status_json"),
        include_ignored_paths=_string_list(arguments, "include_ignored_paths"),
        checkout_most_advanced_branch=_bool_or_default(
            arguments, "checkout_most_advanced_branch", False
        ),
        skill_review_report=None,
        intent=_workflow_intent(arguments, repo_root=repo_root, run_id=run_id),
        inspect_only=_choice(arguments, "mode", "plan", {"plan", "inspect"}) == "inspect",
    )


def _review_outcome(arguments: Mapping[str, object], *, repo_root: Path) -> JourneyOutcome:
    _reject_unknown_arguments(arguments, _review_argument_names())
    return review_mcp_journey_outcome(arguments, repo_root=repo_root)


def _verify_outcome(arguments: Mapping[str, object], *, repo_root: Path) -> JourneyOutcome:
    _reject_unknown_arguments(arguments, _VERIFY_ARGUMENTS)
    run_id = _optional_string(arguments, "run_id") or generated_run_id()
    return verify_journey_outcome(
        repo_root=repo_root,
        run_id=run_id,
        profile=_optional_string(arguments, "profile"),
        ci_status_json=_optional_path(arguments, "ci_status_json"),
        timeout_seconds=_positive_int_or_default(arguments, "timeout_seconds", 120),
        checkout_most_advanced_branch=_bool_or_default(
            arguments, "checkout_most_advanced_branch", False
        ),
        execute_discovered_gates=_bool_or_default(arguments, "execute_gates", False),
        read_only_gates=_bool_or_default(arguments, "read_only_gates", False),
        allow_mutating_gates=_bool_or_default(arguments, "allow_mutating_gates", False),
        worktree_mode=_choice(arguments, "worktree_mode", "in-place", {"in-place", "disposable"}),
        allow_dirty_worktree_verify=_bool_or_default(
            arguments, "allow_dirty_worktree_verify", False
        ),
        skill_review_report=None,
        intent=_workflow_intent(arguments, repo_root=repo_root, run_id=run_id),
    )


def _runs_outcome(arguments: Mapping[str, object], *, repo_root: Path) -> JourneyOutcome:
    _reject_unknown_arguments(arguments, _RUNS_ARGUMENTS)
    return runs_journey_outcome(
        repo_root=repo_root,
        run_id=_optional_string(arguments, "run_id"),
        limit=_bounded_limit(arguments),
    )


def _review_input_schema() -> dict[str, object]:
    return review_mcp_input_schema()


def _review_argument_names() -> frozenset[str]:
    properties = _review_input_schema().get("properties")
    if not isinstance(properties, dict):
        raise RuntimeError("review MCP input schema is missing properties")
    return frozenset(key for key in properties if isinstance(key, str))


def _workflow_intent(
    arguments: Mapping[str, object],
    *,
    repo_root: Path,
    run_id: str,
) -> AuditPayload | None:
    intent = resolve_workflow_intent(
        repo_root=repo_root,
        run_id=run_id,
        goal=_optional_string(arguments, "intent"),
        intent_file=_optional_path(arguments, "intent_file"),
        source="mcp",
        supplied_by="agent",
    )
    return None if intent is None else _intent_payload(intent)


def _intent_payload(intent: Mapping[str, object]) -> AuditPayload:
    return dict(intent)


def _reject_unknown_arguments(arguments: Mapping[str, object], allowed: frozenset[str]) -> None:
    unknown = sorted(set(arguments).difference(allowed))
    if unknown:
        raise ValueError(f"Unsupported arguments: {', '.join(unknown)}")


def _optional_string(arguments: Mapping[str, object], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_path(arguments: Mapping[str, object], key: str) -> Path | None:
    value = _optional_string(arguments, key)
    return Path(value).expanduser().resolve() if value is not None else None


def _string_list(arguments: Mapping[str, object], key: str) -> list[str]:
    value = arguments.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{key} must be an array of non-empty strings")
    return value


def _bool_or_default(arguments: Mapping[str, object], key: str, default: bool) -> bool:
    value = arguments.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _positive_int_or_default(arguments: Mapping[str, object], key: str, default: int) -> int:
    value = arguments.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{key} must be a positive integer")
    return value


def _bounded_limit(arguments: Mapping[str, object]) -> int:
    limit = _positive_int_or_default(arguments, "limit", DEFAULT_HISTORY_LIMIT)
    if limit > MAX_HISTORY_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_HISTORY_LIMIT}")
    return limit


def _choice(
    arguments: Mapping[str, object],
    key: str,
    default: str,
    allowed: set[str],
) -> str:
    value = arguments.get(key, default)
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{key} must be one of: {choices}")
    return value
