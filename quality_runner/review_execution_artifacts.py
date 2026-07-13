from __future__ import annotations

import fcntl
import json
import os
import secrets
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import cast

from quality_runner.application.review_v1_serializers import (
    review_manifest_from_v1,
    review_manifest_to_v1,
    review_packet_from_v1,
    review_packet_to_v1,
    review_report_to_v1,
)
from quality_runner.artifacts import (
    artifact_dir,
    existing_artifact_dir,
    prepare_artifact_dir,
    safe_child_file,
)
from quality_runner.core.review_contracts import (
    CombinedReviewPacket,
    CombinedReviewResponseProvenance,
    ReviewHandoff,
    ReviewManifest,
    ReviewPacket,
    ReviewReport,
    ReviewResponseProvenance,
)
from quality_runner.core.review_packets import (
    MAX_REVIEW_RESPONSE_BYTES,
    response_template,
    validate_prepared_packet,
)
from quality_runner.review_artifacts import (
    render_agent_packet,
    render_combined_agent_packet_guide,
    render_fix_prompts,
    render_review_markdown,
)
from quality_runner.review_response_files import (
    no_follow_flag,
    nonblocking_flag,
    open_checked_directory,
    read_local_adapter_response,
    read_regular_text_file,
)
from quality_runner.schema_constants import (
    REVIEW_ADAPTER_ATTEMPT_SCHEMA,
    REVIEW_EXECUTION_SCHEMA,
    REVIEW_HANDOFF_SCHEMA,
)

_PREPARED_STATE = "packet-ready"
_COMPLETED_STATE = "review-complete"
_MAX_REVIEW_ARTIFACT_BYTES = 4_000_000
_PRIMARY_FILENAMES = (
    "review-manifest.json",
    "review-context.json",
    "review-report.json",
    "review-report.md",
    "review-agent-packet.md",
    "review-fix-prompts.md",
    "review-adapter-response.template.json",
    "review-execution.json",
)
_LEGACY_ARTIFACT_PATHS = (
    "review_manifest_json",
    "review_context_json",
    "review_report_json",
    "review_report_md",
    "review_agent_packet_md",
    "review_fix_prompts_md",
)


def legacy_review_artifact_paths(repo_root: Path, run_id: str) -> dict[str, str]:
    run_dir = artifact_dir(repo_root, run_id)
    paths = _paths(run_dir)
    return {name: str(paths[name]) for name in _LEGACY_ARTIFACT_PATHS}


def prepare_review_execution_artifacts(
    *,
    repo_root: Path,
    context: ReviewPacket,
    manifest: ReviewManifest,
    report: ReviewReport,
) -> dict[str, str]:
    """Persist an immutable packet-ready review before any adapter reads it."""
    run_dir = prepare_artifact_dir(repo_root, context["run_id"])
    paths = _paths(run_dir)
    _reject_existing_prepared_artifacts(paths)
    context_payload = review_packet_to_v1(context)
    manifest_payload = review_manifest_to_v1(manifest)
    report_payload = review_report_to_v1(report)
    _atomic_write_json(paths["review_manifest_json"], manifest_payload)
    _atomic_write_json(paths["review_context_json"], context_payload)
    _write_agent_packets(paths=paths, context=context, context_payload=context_payload)
    _atomic_write_json(paths["review_adapter_response_template_json"], response_template(context))
    _atomic_write_json(paths["review_report_json"], report_payload)
    _atomic_write_text(paths["review_report_md"], render_review_markdown(report_payload))
    _atomic_write_text(
        paths["review_fix_prompts_md"],
        render_fix_prompts(report_payload, selected_findings=[]),
    )
    _atomic_write_json(
        paths["review_execution_json"],
        _execution_payload(context=context, state=_PREPARED_STATE, handoff=_not_ready_handoff()),
    )
    return _existing_string_paths(paths)


def load_prepared_review(
    *, repo_root: Path, run_id: str
) -> tuple[ReviewPacket, ReviewManifest, dict[str, object], dict[str, str]]:
    run_dir = existing_artifact_dir(repo_root, run_id)
    paths = _paths(run_dir)
    context_payload = _load_json(paths["review_context_json"])
    manifest_payload = _load_json(paths["review_manifest_json"])
    execution_payload = _load_json(paths["review_execution_json"])
    context = cast(ReviewPacket, review_packet_from_v1(context_payload))
    manifest = review_manifest_from_v1(manifest_payload)
    validate_prepared_packet(context)
    _validate_prepared_manifest(manifest, context, repo_root)
    _validate_prepared_execution(execution_payload, context)
    return context, manifest, execution_payload, _existing_string_paths(paths)


def read_review_adapter_response(
    *, repo_root: Path, run_id: str, response_path: Path
) -> dict[str, object]:
    """Read one direct, non-symlink response file from the prepared run directory."""
    run_dir = existing_artifact_dir(repo_root, run_id)
    return read_local_adapter_response(
        allowed_directory=run_dir,
        response_path=response_path,
        relative_root=repo_root,
        maximum_bytes=MAX_REVIEW_RESPONSE_BYTES,
    )


def complete_review_execution_artifacts(
    *,
    repo_root: Path,
    context: ReviewPacket,
    report: ReviewReport,
    handoff: ReviewHandoff,
    response_payload: Mapping[str, object],
    response_provenance: ReviewResponseProvenance | CombinedReviewResponseProvenance,
) -> dict[str, str]:
    """Finalize only a packet-ready run after a bound adapter response validates."""
    run_dir = existing_artifact_dir(repo_root, context["run_id"])
    with _finalization_lock(run_dir):
        stored_context, _, execution, _ = load_prepared_review(
            repo_root=repo_root, run_id=context["run_id"]
        )
        if review_packet_to_v1(stored_context) != review_packet_to_v1(context):
            raise ValueError("prepared review context changed before finalization")
        _validate_prepared_execution(execution, context)
        paths = _paths(run_dir)
        report_payload = review_report_to_v1(report)
        _atomic_write_json(paths["review_adapter_response_json"], dict(response_payload))
        _atomic_write_json(paths["review_report_json"], report_payload)
        _atomic_write_text(paths["review_report_md"], render_review_markdown(report_payload))
        _atomic_write_text(
            paths["review_fix_prompts_md"],
            render_fix_prompts(report_payload, selected_findings=handoff["selected_findings"]),
        )
        _atomic_write_json(paths["review_fix_handoff_json"], _handoff_payload(context, handoff))
        loop_state = handoff.get("loop_state")
        if loop_state is not None:
            _atomic_write_json(paths["review_loop_state_json"], loop_state)
        _atomic_write_json(
            paths["review_execution_json"],
            _execution_payload(
                context=context,
                state=_COMPLETED_STATE,
                handoff=handoff,
                response_provenance=response_provenance,
            ),
        )
        return _existing_string_paths(paths)


def record_review_execution_failure(
    *, repo_root: Path, run_id: str, report: ReviewReport, message: str
) -> dict[str, str]:
    """Record a rejected response without finalizing or replacing the immutable packet."""
    run_dir = existing_artifact_dir(repo_root, run_id)
    with _finalization_lock(run_dir):
        context, _, execution, _ = load_prepared_review(repo_root=repo_root, run_id=run_id)
        _validate_prepared_execution(execution, context)
        paths = _paths(run_dir)
        report_payload = review_report_to_v1(report)
        _atomic_write_json(paths["review_report_json"], report_payload)
        _atomic_write_text(paths["review_report_md"], render_review_markdown(report_payload))
        _atomic_write_text(
            paths["review_fix_prompts_md"], render_fix_prompts(report_payload, selected_findings=[])
        )
        _atomic_write_json(
            paths["review_adapter_attempt_json"],
            {
                "schema": REVIEW_ADAPTER_ATTEMPT_SCHEMA,
                "run_id": run_id,
                "status": report["adapter_status"],
                "message": message,
            },
        )
        return _existing_string_paths(paths)


def _paths(run_dir: Path) -> dict[str, Path]:
    return {
        "review_manifest_json": run_dir / "review-manifest.json",
        "review_context_json": run_dir / "review-context.json",
        "review_report_json": run_dir / "review-report.json",
        "review_report_md": run_dir / "review-report.md",
        "review_agent_packet_md": run_dir / "review-agent-packet.md",
        "review_agent_task_packet_md": run_dir / "review-agent-packet-task.md",
        "review_agent_blind_packet_md": run_dir / "review-agent-packet-blind.md",
        "review_fix_prompts_md": run_dir / "review-fix-prompts.md",
        "review_adapter_response_template_json": run_dir / "review-adapter-response.template.json",
        "review_adapter_response_json": run_dir / "review-adapter-response.json",
        "review_execution_json": run_dir / "review-execution.json",
        "review_fix_handoff_json": run_dir / "review-fix-handoff.json",
        "review_loop_state_json": run_dir / "review-loop-state.json",
        "review_adapter_attempt_json": run_dir / "review-adapter-attempt.json",
    }


def _write_agent_packets(
    *, paths: Mapping[str, Path], context: ReviewPacket, context_payload: Mapping[str, object]
) -> None:
    if context["mode"] != "combined":
        _atomic_write_text(paths["review_agent_packet_md"], render_agent_packet(context_payload))
        return
    combined = cast(CombinedReviewPacket, context)
    task_packet, blind_packet = combined["packets"]
    _atomic_write_text(paths["review_agent_packet_md"], render_combined_agent_packet_guide())
    _atomic_write_text(paths["review_agent_task_packet_md"], render_agent_packet(dict(task_packet)))
    _atomic_write_text(
        paths["review_agent_blind_packet_md"], render_agent_packet(dict(blind_packet))
    )


def _reject_existing_prepared_artifacts(paths: Mapping[str, Path]) -> None:
    existing = [
        filename
        for filename in _PRIMARY_FILENAMES
        if safe_child_file(paths["review_execution_json"].parent, filename).exists()
    ]
    if existing:
        raise ValueError(
            "review run already contains prepared evidence; use its run id with --adapter-output "
            "or start a new run"
        )


def _execution_payload(
    *,
    context: ReviewPacket,
    state: str,
    handoff: ReviewHandoff,
    response_provenance: ReviewResponseProvenance | CombinedReviewResponseProvenance | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": REVIEW_EXECUTION_SCHEMA,
        "run_id": context["run_id"],
        "state": state,
        "mode": context["mode"],
        "input_hashes": dict(context["input_hashes"]),
        "context_access": "advisory-exclusions-for-local-file-adapter",
        "handoff": _handoff_payload(context, handoff),
    }
    if response_provenance is not None:
        payload["response_provenance"] = dict(response_provenance)
    return payload


def _handoff_payload(context: ReviewPacket, handoff: ReviewHandoff) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": REVIEW_HANDOFF_SCHEMA,
        "run_id": context["run_id"],
        "status": handoff["status"],
        "selected_finding_ids": list(handoff["selected_finding_ids"]),
        "selected_findings": [dict(finding) for finding in handoff["selected_findings"]],
    }
    if "loop_state" in handoff:
        payload["loop_state"] = dict(handoff["loop_state"])
    if "next_action" in handoff:
        payload["next_action"] = handoff["next_action"]
    return payload


def _not_ready_handoff() -> ReviewHandoff:
    return {
        "status": "not-ready",
        "selected_finding_ids": [],
        "selected_findings": [],
        "next_action": "Provide a bound adapter response before preparing a fixing handoff.",
    }


def _validate_prepared_execution(payload: Mapping[str, object], context: ReviewPacket) -> None:
    if payload.get("schema") != REVIEW_EXECUTION_SCHEMA:
        raise ValueError("review execution state does not match its schema")
    if payload.get("state") != _PREPARED_STATE:
        raise ValueError(
            "review run is already finalized and cannot accept another adapter response"
        )
    if payload.get("run_id") != context["run_id"] or payload.get("mode") != context["mode"]:
        raise ValueError("review execution state does not match the prepared context")
    input_hashes = payload.get("input_hashes")
    if not isinstance(input_hashes, Mapping) or dict(input_hashes) != context["input_hashes"]:
        raise ValueError("review execution state does not match the prepared context hashes")


def _validate_prepared_manifest(
    manifest: ReviewManifest,
    context: ReviewPacket,
    repo_root: Path,
) -> None:
    if (
        manifest["run_id"] != context["run_id"]
        or manifest["mode"] != context["mode"]
        or manifest["scope"] != context["scope"]
        or manifest["breadth"] != context["breadth"]
        or manifest["exclusions"] != context["exclusions"]
        or manifest["evidence_references"] != context["evidence"]
        or manifest["freshness"] != context["freshness"]
        or manifest["input_hashes"] != context["input_hashes"]
    ):
        raise ValueError("review manifest does not match the prepared context")
    if manifest["artifact_paths"] != legacy_review_artifact_paths(repo_root, context["run_id"]):
        raise ValueError("review manifest does not match the legacy artifact contract")


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(read_regular_text_file(path, maximum_bytes=_MAX_REVIEW_ARTIFACT_BYTES))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"review artifact is not readable JSON: {error}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("review artifact must be a JSON object")
    return dict(payload)


@contextmanager
def _finalization_lock(run_dir: Path) -> Iterator[None]:
    directory_descriptor = open_checked_directory(run_dir)
    descriptor: int | None = None
    locked = False
    try:
        descriptor = os.open(
            ".review-execution.lock",
            os.O_WRONLY | os.O_CREAT | nonblocking_flag() | no_follow_flag(),
            0o600,
            dir_fd=directory_descriptor,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("review finalization lock must be a regular file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except BlockingIOError as error:
            raise ValueError("a review response is already being finalized for this run") from error
        os.ftruncate(descriptor, 0)
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        yield
    finally:
        if descriptor is not None:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
        os.close(directory_descriptor)


def _string_paths(paths: Mapping[str, Path]) -> dict[str, str]:
    return {name: str(path) for name, path in paths.items()}


def _existing_string_paths(paths: Mapping[str, Path]) -> dict[str, str]:
    return {name: str(path) for name, path in paths.items() if path.exists()}


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    _atomic_write_text(path, json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")


def _atomic_write_text(path: Path, content: str) -> None:
    target = safe_child_file(path.parent, path.name)
    directory_descriptor = open_checked_directory(target.parent)
    temporary_name = f".{target.name}.{secrets.token_hex(12)}"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | no_follow_flag(),
            0o600,
            dir_fd=directory_descriptor,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = None
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name,
            target.name,
            src_dir_fd=directory_descriptor,
            dst_dir_fd=directory_descriptor,
        )
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            os.unlink(temporary_name, dir_fd=directory_descriptor)
        os.close(directory_descriptor)
