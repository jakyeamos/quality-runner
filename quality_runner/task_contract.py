from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from quality_runner import __version__
from quality_runner.config import CONFIG_FILE_NAME

TASK_ANALYSIS_MODE = "full"
TASK_CACHE_MODE = "external"
TASK_CHECK_MODE_AUTHORITATIVE = "authoritative"
TASK_CHECK_MODE_FAST = "fast"
TASK_RELEASE_ENFORCEMENT_ADVISORY = "advisory"
TASK_RELEASE_ENFORCEMENT_REQUIRED = "required"


def task_next_action(
    status: str,
    *,
    mode: str = TASK_CHECK_MODE_AUTHORITATIVE,
    enforcement: str = TASK_RELEASE_ENFORCEMENT_ADVISORY,
) -> str:
    if mode == TASK_CHECK_MODE_FAST:
        actions = {
            "pass": (
                "Fast Quality Runner feedback passes. Run `qr task release-check` before "
                "declaring the implementation complete."
            ),
            "violation": (
                "Fix every new enforced finding, or record an eligible exact-fingerprint "
                "disposition, then rerun `qr task check --fast`; run "
                "`qr task release-check` before completion."
            ),
            "blocked": (
                "Resolve every blocker, using `qr task rebaseline` with an explicit reason "
                "only when the evidence contract changed, then rerun `qr task check --fast` "
                "and `qr task release-check`."
            ),
        }
        return actions.get(status, task_next_action(status))
    if enforcement == TASK_RELEASE_ENFORCEMENT_REQUIRED:
        actions = {
            "pass": (
                "Quality Runner release evidence passes. Complete any remaining "
                "repository-required checks before declaring the implementation complete."
            ),
            "violation": (
                "Fix every new enforced finding and failed certified gate, or record an "
                "eligible exact-fingerprint disposition, then rerun "
                "`qr task release-check`."
            ),
            "blocked": (
                "Resolve every blocker, using `qr task rebaseline` with an explicit reason "
                "only when the evidence contract changed, then rerun "
                "`qr task release-check`."
            ),
        }
        return actions.get(status, task_next_action(status))
    actions = {
        "pass": (
            "Quality Runner evidence passes. Complete any remaining repository-required "
            "checks before declaring the implementation complete."
        ),
        "violation": (
            "Fix every new enforced finding and failed certified gate, or record an eligible "
            "exact-fingerprint disposition, then rerun `qr task check`."
        ),
        "blocked": (
            "Resolve every blocker, using `qr task rebaseline` with an explicit reason only "
            "when the evidence contract changed, then rerun `qr task check`."
        ),
        "invalid": (
            "Correct the task invocation or prevention configuration, then rerun the task command."
        ),
    }
    return actions.get(status, actions["invalid"])


def release_readiness(
    *,
    mode: str,
    delta: dict[str, Any],
    repository_blockers: list[dict[str, str]],
    contract_blockers: list[dict[str, str]],
    promotion_blockers: list[dict[str, str]],
    gate_blockers: list[dict[str, str]],
    readiness_blockers: list[dict[str, str]],
    required_gate_failures: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = cast(dict[str, int], delta.get("counts", {}))
    delta_blockers = cast(list[dict[str, str]], delta.get("blockers", []))
    criteria = {
        "authoritative_check": mode == TASK_CHECK_MODE_AUTHORITATIVE,
        "no_new_enforced_findings": counts.get("new_enforced", 0) == 0,
        "no_unknown_findings": counts.get("unknown", 0) == 0,
        "comparable_coverage_complete": not any(
            item.get("code") in {"required_coverage_incomplete", "incomplete_comparable_coverage"}
            for item in delta_blockers
        ),
        "finding_delta_valid": not delta_blockers,
        "evidence_contract_unchanged": not contract_blockers,
        "repository_identity_matches": not repository_blockers,
        "promotion_evidence_complete": not promotion_blockers,
        "required_certified_gates_passed": (
            mode == TASK_CHECK_MODE_AUTHORITATIVE
            and not gate_blockers
            and not readiness_blockers
            and not required_gate_failures
        ),
    }
    blocking_reasons = [name for name, passed in criteria.items() if not passed]
    return {
        "status": "ready" if not blocking_reasons else "ineligible",
        "eligible": not blocking_reasons,
        "mode": mode,
        "predicate": "no_new_enforced_findings",
        "criteria": criteria,
        "blocking_reasons": blocking_reasons,
    }


def enforce_release_eligibility(
    *,
    decision: str,
    enforcement: str,
    readiness: dict[str, Any],
    blockers: list[dict[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    if enforcement != TASK_RELEASE_ENFORCEMENT_REQUIRED or readiness.get("eligible") is True:
        return decision, blockers
    if decision != "pass":
        return decision, blockers
    return (
        "blocked",
        [
            *blockers,
            {
                "code": "release_readiness_ineligible",
                "message": "release-check requires every release readiness criterion to pass",
            },
        ],
    )


def contract_hashes(repo_root: Path, config: dict[str, Any]) -> dict[str, str]:
    config_path = repo_root / CONFIG_FILE_NAME
    config_content = config_path.read_bytes() if config_path.is_file() else b"<absent>"
    prevention = config.get("prevention")
    prevention = cast(dict[str, Any], prevention) if isinstance(prevention, dict) else {}
    return {
        "quality_runner_version": __version__,
        "configuration_hash": hashlib.sha256(config_content).hexdigest(),
        "promoted_policy_hash": hash_payload(prevention),
        "rule_pack_hash": rule_pack_hash(),
    }


def drift_blockers(
    baseline: dict[str, Any],
    repo_root: Path,
    config: dict[str, Any],
    readiness: dict[str, Any],
) -> list[dict[str, str]]:
    current = {
        **contract_hashes(repo_root, config),
        "toolchain_hash": readiness["toolchain_hash"],
        "task_analysis_mode": TASK_ANALYSIS_MODE,
        "task_cache_mode": TASK_CACHE_MODE,
    }
    previous = cast(dict[str, str], baseline.get("evidence", {}))
    labels = {
        "quality_runner_version": "Quality Runner version",
        "configuration_hash": "configuration",
        "promoted_policy_hash": "promoted policy",
        "rule_pack_hash": "rule pack",
        "toolchain_hash": "toolchain",
        "task_analysis_mode": "task analysis mode",
        "task_cache_mode": "task cache mode",
    }
    return [
        {
            "code": "rebaseline_required",
            "message": f"{labels[key]} changed after task start",
        }
        for key in labels
        if previous.get(key) != current.get(key)
    ]


def render_task_check_markdown(payload: dict[str, Any]) -> str:
    delta = cast(dict[str, Any], payload["delta"])
    counts = cast(dict[str, int], delta["counts"])
    readiness = cast(dict[str, Any], payload["release_readiness"])
    lines = [
        f"# Quality Runner task check: {payload['task_id']}",
        "",
        f"- Status: **{payload['status']}**",
        f"- Mode: **{payload['mode']}**",
        f"- Release enforcement: **{payload['release_enforcement']}**",
        f"- Release readiness: **{readiness['status']}**",
        f"- Baseline: `{payload['baseline_run_id']}`",
        f"- Check run: `{payload['run_id']}`",
        f"- Changed paths: {len(cast(list[str], payload['changed_paths']))}",
        "",
        "## Next action",
        "",
        str(payload["next_action"]),
        "",
        "## Finding delta",
        "",
    ]
    for bucket in (
        "new_enforced",
        "persisted",
        "resolved",
        "waived",
        "advisory",
        "out_of_scope",
        "unknown",
    ):
        lines.append(f"- {bucket}: {counts[bucket]}")
    lines.extend(["", "## Native gates", ""])
    gate_results = cast(list[dict[str, Any]], payload["gate_results"])
    if gate_results:
        lines.extend(f"- {item['id']}: {item['status']}" for item in gate_results)
    else:
        lines.append("- No certified gates executed.")
    blockers = cast(list[dict[str, str]], payload["blockers"])
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{item['code']}`: {item['message']}" for item in blockers)
    return "\n".join(lines) + "\n"


def deduplicate_blockers(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"code": code, "message": message}
        for code, message in sorted({(item["code"], item["message"]) for item in items})
    ]


def hash_payload(value: object) -> str:
    content = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(content).hexdigest()


def rule_pack_hash() -> str:
    root = Path(__file__).resolve().parent
    paths = [
        *root.glob("code_quality*.py"),
        root / "task_findings.py",
        root / "security" / "candidates.py",
        root / "security" / "taxonomy.py",
    ]
    digest = hashlib.sha256()
    for path in sorted({item for item in paths if item.is_file()}):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()
