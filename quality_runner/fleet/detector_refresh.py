from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from quality_runner._version import __version__
from quality_runner.artifacts import prepare_safe_directory, write_json
from quality_runner.fleet.anti_slop import (
    ANTI_SLOP_DETECTOR,
    ANTI_SLOP_PRESET,
    ANTI_SLOP_SOURCE_SHA,
    merge_anti_slop_scan,
    run_anti_slop_detector,
)
from quality_runner.fleet.contracts import parse_as_of, stable_id
from quality_runner.fleet.detector_publication import publish_detector_runs
from quality_runner.fleet.discovery import (
    discover_repositories,
    repository_record_for_root,
    resolve_target_branch,
)
from quality_runner.fleet.repository_lifecycle import (
    documented_archival_repository,
    documented_deprecated_repository,
)
from quality_runner.workflow import refresh_payload

DETECTOR_REFRESH_SCHEMA = "quality-runner-fleet-detector-refresh/v1"
DEFAULT_DETECTOR_REFRESH_ROOT = Path("~/.quality-runner/fleet-detector-refresh")
RefreshCallback = Callable[..., dict[str, Any]]


def fleet_detector_refresh_payload(
    *,
    projects_root: Path,
    output_dir: Path | None = None,
    repository_paths: Sequence[Path] | None = None,
    target_overrides: dict[str, str] | None = None,
    timeout_seconds: int = 600,
    agent_review_mode: str = "off",
    as_of: str | None = None,
    anti_slop_root: Path | None = None,
    anti_slop_preset: str = ANTI_SLOP_PRESET,
    anti_slop_format: str = "json",
    refresh_callback: RefreshCallback = refresh_payload,
) -> dict[str, Any]:
    """Run full detector scans at exact target commits and publish normal QR runs.

    The fleet ledger is runtime-owned. Published detector evidence uses the existing
    repository-local ``.quality-runner/runs`` contract consumed by Pronto.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if agent_review_mode not in {"off", "auto", "parallel", "required"}:
        raise ValueError("agent_review_mode must be off, auto, parallel, or required")
    resolved_as_of = parse_as_of(as_of)
    root = projects_root.expanduser().resolve()
    overrides = target_overrides or {}
    refresh_id = stable_id(
        "detector-refresh",
        str(root),
        resolved_as_of,
        sorted(overrides.items()),
        sorted(str(path.expanduser().resolve()) for path in repository_paths or []),
        str(anti_slop_root.expanduser().resolve()) if anti_slop_root is not None else None,
        anti_slop_preset,
        anti_slop_format,
        ANTI_SLOP_SOURCE_SHA if anti_slop_root is not None else None,
    )
    artifact_root = _artifact_root(output_dir, refresh_id)
    prepare_safe_directory(artifact_root)
    repositories = _repositories_for_scope(root, repository_paths)
    results: list[dict[str, Any]] = []
    for repository in repositories:
        try:
            result = _refresh_repository(
                repository=repository,
                target_override=_target_override(repository, overrides),
                refresh_id=refresh_id,
                as_of=resolved_as_of,
                artifact_root=artifact_root,
                timeout_seconds=timeout_seconds,
                agent_review_mode=agent_review_mode,
                anti_slop_root=anti_slop_root,
                anti_slop_preset=anti_slop_preset,
                anti_slop_format=anti_slop_format,
                refresh_callback=refresh_callback,
            )
        except Exception as error:  # preserve one ledger row and continue the fleet
            result = {
                "repo_id": repository.get("repo_id"),
                "primary_path": repository.get("primary_path"),
                "status": "blocked",
                "reason": f"unexpected detector refresh failure: {type(error).__name__}: {error}",
            }
        results.append(result)
    counts = {
        status: sum(result["status"] == status for result in results)
        for status in ("published", "blocked", "unsupported")
    }
    payload = {
        "schema": DETECTOR_REFRESH_SCHEMA,
        "status": "completed" if counts["blocked"] == 0 else "partial",
        "refresh_id": refresh_id,
        "as_of": resolved_as_of,
        "projects_root": str(root),
        "analysis": {
            "mode": "full",
            "skill_packs": "enabled",
            "agent_review_mode": agent_review_mode,
            "execute_discovered_gates": False,
            "external_detectors": {
                ANTI_SLOP_DETECTOR: {
                    "status": "enabled" if anti_slop_root is not None else "disabled",
                    "producer_source_sha": ANTI_SLOP_SOURCE_SHA
                    if anti_slop_root is not None
                    else None,
                    "preset": anti_slop_preset if anti_slop_root is not None else None,
                    "format": anti_slop_format if anti_slop_root is not None else None,
                }
            },
        },
        "publication": {
            "contract": "repository-local-quality-runner-runs",
            "consumer_next_step": "pronto quality refresh --json",
        },
        "repository_count": len(results),
        "counts": counts,
        "results": results,
        "artifact_root": str(artifact_root),
        "implementation_allowed": False,
    }
    ledger = write_json(artifact_root / "detector-refresh.json", payload)
    payload["artifact_paths"] = {"ledger_json": str(ledger)}
    return payload


def _refresh_repository(
    *,
    repository: dict[str, Any],
    target_override: str | None,
    refresh_id: str,
    as_of: str,
    artifact_root: Path,
    timeout_seconds: int,
    agent_review_mode: str,
    anti_slop_root: Path | None,
    anti_slop_preset: str,
    anti_slop_format: str,
    refresh_callback: RefreshCallback,
) -> dict[str, Any]:
    repo_id = str(repository["repo_id"])
    target = _resolve_detector_target(repository, override=target_override)
    result: dict[str, Any] = {
        "repo_id": repo_id,
        "primary_path": repository.get("primary_path"),
        "status": "blocked",
        "target": target,
    }
    if target.get("status") != "ready":
        result["reason"] = target.get("reason", "target branch is not ready")
        return result
    source_checkout = next(
        (
            checkout
            for checkout in repository.get("checkouts", [])
            if checkout.get("checkout_id") == target.get("checkout_id")
        ),
        None,
    )
    if not isinstance(source_checkout, dict) or not source_checkout.get("path"):
        result["reason"] = "target checkout record is missing"
        return result
    source = Path(str(source_checkout["path"])).expanduser().resolve()
    publication_root = Path(str(repository["primary_path"])).expanduser().resolve()
    worktree = artifact_root / "worktrees" / repo_id
    before_head = _git_output(source, "rev-parse", "HEAD")
    if worktree.exists() or worktree.is_symlink():
        result["reason"] = "runtime-owned disposable worktree path already exists"
        return result
    prepare_safe_directory(worktree.parent)
    setup = _git(source, "worktree", "add", "--detach", str(worktree), str(target["head"]))
    if setup.returncode != 0 or not worktree.is_dir():
        result["reason"] = (setup.stderr or setup.stdout).strip()[:500]
        _git(source, "worktree", "remove", "--force", str(worktree))
        return result
    try:
        if documented_deprecated_repository(worktree):
            result.update(
                status="unsupported",
                reason="repository documentation declares a deprecated historical checkout",
            )
            return result
        if documented_archival_repository(worktree):
            result.update(
                status="unsupported",
                reason="repository documentation declares an archival generated snapshot",
            )
            return result
        run_prefix = _run_prefix(as_of, repo_id)
        try:
            refresh = refresh_callback(
                repo_root=worktree,
                run_id_prefix=run_prefix,
                timeout_seconds=min(timeout_seconds, 120),
                inspect_timeout_seconds=timeout_seconds,
                run_timeout_seconds=timeout_seconds,
                verify_timeout_seconds=timeout_seconds,
                total_timeout_seconds=timeout_seconds,
                total_timeout_reason="fleet detector refresh repository deadline",
                execute_discovered_gates=False,
                worktree_mode="in-place",
                analysis_mode="full",
                cache_mode="external",
                cache_root=artifact_root / "cache" / repo_id,
                agent_review_mode=agent_review_mode,
            )
        except Exception as error:  # fleet lane must continue to the next repository
            result["reason"] = f"full detector refresh failed: {type(error).__name__}: {error}"
            return result
        run_ids = [f"{run_prefix}-{suffix}" for suffix in ("inspect", "run", "verify")]
        result["refresh_status"] = refresh.get("status")
        diagnostics = _incomplete_refresh_diagnostics(
            refresh=refresh,
            worktree=worktree,
            run_ids=run_ids,
        )
        if diagnostics is not None:
            result["refresh_diagnostics"] = diagnostics
            result["reason"] = _incomplete_refresh_reason(diagnostics)
            return result
        detector_result: dict[str, Any] | None = None
        if anti_slop_root is not None:
            detector_result = run_anti_slop_detector(
                target_root=worktree,
                target_sha=str(target["head"]),
                qr_version=__version__,
                anti_slop_root=anti_slop_root,
                preset=anti_slop_preset,
                output_format=anti_slop_format,
                timeout_seconds=timeout_seconds,
                cache_root=artifact_root / "cache" / repo_id,
            )
            result["detector"] = detector_result.get("receipt")
            if detector_result.get("status") == "blocked":
                result["reason"] = (
                    "external anti-slop detector blocked evidence: "
                    f"{detector_result.get('reason', 'unknown detector failure')}"
                )
                return result
        try:
            if detector_result is not None:
                _merge_external_detector(
                    worktree=worktree,
                    run_ids=run_ids,
                    detector_result=detector_result,
                )
            published = publish_detector_runs(
                worktree=worktree,
                publication_root=publication_root,
                run_ids=run_ids,
                target_branch=str(target["branch"]),
                target_head=str(target["head"]),
                detector_provenance=(
                    [detector_result["receipt"]]
                    if detector_result is not None
                    and isinstance(detector_result.get("receipt"), dict)
                    else []
                ),
            )
            finding_count = _finding_count(publication_root, run_ids)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            result["reason"] = f"detector evidence publication failed: {error}"
            return result
        result.update(
            status="published",
            reason="full exact-target detector evidence published",
            run_ids=run_ids,
            published_paths=published,
            finding_count=finding_count,
        )
        return result
    finally:
        cleanup = _git(source, "worktree", "remove", "--force", str(worktree))
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)
        result["cleanup"] = {
            "status": "passed" if cleanup.returncode == 0 and not worktree.exists() else "failed",
            "returncode": cleanup.returncode,
        }
        after_head = _git_output(source, "rev-parse", "HEAD")
        result["source_head_unchanged"] = before_head == after_head
        if result["cleanup"]["status"] != "passed" or not result["source_head_unchanged"]:
            result["status"] = "blocked"
            result["reason"] = "disposable worktree cleanup or source HEAD integrity failed"


def _incomplete_refresh_diagnostics(
    *, refresh: dict[str, Any], worktree: Path, run_ids: list[str]
) -> dict[str, Any] | None:
    run_root = worktree / ".quality-runner" / "runs"
    missing_run_ids = [run_id for run_id in run_ids if not (run_root / run_id).is_dir()]
    if not missing_run_ids:
        return None

    phase_payloads = refresh.get("runs")
    timings = refresh.get("phase_timings")
    phases: dict[str, dict[str, Any]] = {}
    for phase in ("inspect", "run", "verify"):
        compact: dict[str, Any] = {}
        if isinstance(phase_payloads, dict) and isinstance(phase_payloads.get(phase), dict):
            phase_payload = phase_payloads[phase]
            for key in ("run_id", "status", "reason", "timeout_scope", "timeout_seconds"):
                value = phase_payload.get(key)
                if value is not None and isinstance(value, (str, int, float, bool)):
                    compact[key] = value
        if isinstance(timings, dict) and isinstance(timings.get(phase), dict):
            timing_status = timings[phase].get("status")
            if isinstance(timing_status, str):
                compact["timing_status"] = timing_status
        if compact:
            phases[phase] = compact
    diagnostics: dict[str, Any] = {
        "status": refresh.get("status"),
        "missing_run_ids": missing_run_ids,
    }
    if phases:
        diagnostics["phases"] = phases
    return diagnostics


def _incomplete_refresh_reason(diagnostics: dict[str, Any]) -> str:
    phases = diagnostics.get("phases")
    if isinstance(phases, dict):
        for phase in ("inspect", "run", "verify"):
            details = phases.get(phase)
            if not isinstance(details, dict):
                continue
            status = details.get("status") or details.get("timing_status")
            reason = details.get("reason")
            if status not in {None, "completed", "passed"} or reason:
                summary = f"{phase} phase {status or 'incomplete'}"
                if isinstance(reason, str) and reason:
                    summary = f"{summary}: {reason}"
                return f"full detector refresh incomplete; {summary}"
    missing = diagnostics.get("missing_run_ids")
    return f"full detector refresh incomplete; missing expected runs: {missing}"


def _target_override(repository: dict[str, Any], overrides: dict[str, str]) -> str | None:
    repo_id = str(repository["repo_id"])
    primary_path = str(repository["primary_path"])
    return overrides.get(repo_id) or overrides.get(primary_path)


def _repositories_for_scope(
    projects_root: Path, repository_paths: Sequence[Path] | None
) -> list[dict[str, Any]]:
    if repository_paths is None:
        return discover_repositories(projects_root)
    root = projects_root.expanduser().resolve()
    records: dict[str, dict[str, Any]] = {}
    for path in repository_paths:
        resolved = path.expanduser().resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise ValueError(
                f"repository path is outside the bounded projects root: {resolved}"
            ) from error
        record = repository_record_for_root(resolved)
        records[str(record["repo_id"])] = record
    return [records[repo_id] for repo_id in sorted(records)]


def _resolve_detector_target(repository: dict[str, Any], *, override: str | None) -> dict[str, Any]:
    target = resolve_target_branch(repository, override=override)
    if target.get("status") == "ready" or not target.get("branch"):
        return target
    branch = str(target["branch"])
    checkouts = [
        checkout
        for checkout in repository.get("checkouts", [])
        if isinstance(checkout, dict)
        and branch in checkout.get("local_branches", [])
        and checkout.get("path")
    ]
    checkouts.sort(
        key=lambda checkout: (checkout.get("primary") is not True, str(checkout["path"]))
    )
    if not checkouts:
        return target
    checkout = checkouts[0]
    source = Path(str(checkout["path"])).expanduser().resolve()
    head = _git_output(source, "rev-parse", f"refs/heads/{branch}")
    if not head:
        return target
    return {
        "branch": branch,
        "source": target.get("source"),
        "status": "ready",
        "reason": "exact local branch commit resolved for detached detector worktree",
        "checkout_id": checkout.get("checkout_id"),
        "head": head,
        "target_state": {
            "status": "ready",
            "reason": "detector lane does not require the target branch to be attached",
        },
    }


def _merge_external_detector(
    *, worktree: Path, run_ids: list[str], detector_result: dict[str, Any]
) -> None:
    receipt = detector_result.get("receipt")
    if not isinstance(receipt, dict):
        raise ValueError("external detector result is missing provenance")
    for run_id in run_ids:
        scan_path = worktree / ".quality-runner" / "runs" / run_id / "code-quality-scan.json"
        if not scan_path.is_file():
            raise ValueError(f"external detector scan target is missing: {scan_path}")
        payload = json.loads(scan_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"external detector scan target is not an object: {scan_path}")
        merged = merge_anti_slop_scan(payload, detector_result)
        write_json(scan_path, merged)
        write_json(
            scan_path.parent / "anti-slop-detector.json",
            {"schema": "quality-runner-anti-slop-detector/v1", **receipt},
        )


def _finding_count(root: Path, run_ids: list[str]) -> int | None:
    for run_id in run_ids:
        path = root / ".quality-runner" / "runs" / run_id / "code-quality-scan.json"
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        findings = payload.get("findings")
        if isinstance(findings, list):
            return len(findings)
    return None


def _run_prefix(as_of: str, repo_id: str) -> str:
    stamp = datetime.fromisoformat(as_of.replace("Z", "+00:00")).strftime("%Y%m%dT%H%M%SZ")
    return f"fleet-detector-{stamp}-{repo_id}"


def _artifact_root(output_dir: Path | None, refresh_id: str) -> Path:
    if output_dir is not None:
        base = output_dir.expanduser().resolve()
        return base if base.name == refresh_id else base / refresh_id
    return DEFAULT_DETECTOR_REFRESH_ROOT.expanduser().resolve() / refresh_id


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(root), *args]
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else error.stdout or ""
        stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else error.stderr or ""
        return subprocess.CompletedProcess(
            command,
            124,
            stdout=stdout,
            stderr=stderr or "git command timed out after 30 seconds",
        )


def _git_output(root: Path, *args: str) -> str | None:
    result = _git(root, *args)
    return result.stdout.strip() if result.returncode == 0 else None
