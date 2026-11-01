from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from quality_runner.artifacts import existing_artifact_dir
from quality_runner.model_audit.contracts import (
    PREFIX,
    array_value,
    digest,
    exact_keys,
    object_value,
    text,
)
from quality_runner.model_audit.verification import verified_findings
from quality_runner.model_audit.workflow import load_manifest, load_result

STATUSES = ("newly_verified", "known", "disputed", "unverified", "not_reobserved")


def _lineage(repo: Path, run_id: str) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    lineage: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    seen: set[str] = set()
    expected_digest: str | None = None
    while run_id:
        if run_id in seen or len(seen) >= 64:
            raise ValueError("audit lineage is cyclic or exceeds 64 runs")
        seen.add(run_id)
        manifest = load_manifest(repo, run_id)
        if expected_digest is not None and manifest["digest"] != expected_digest:
            raise ValueError("baseline manifest digest mismatch")
        result = load_result(repo, run_id, manifest)
        findings = verified_findings(existing_artifact_dir(repo, run_id), manifest, result)
        lineage.append((manifest, findings))
        run_id = manifest["baseline_run_id"]
        expected_digest = manifest["baseline_manifest_digest"]
    return list(reversed(lineage))


def _comparison(manifest: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any]:
    if baseline is None:
        return {"kind": "initial", "controlled_model_comparison": False, "confounders": []}
    same_profile = manifest["profile_digest"] == baseline["profile_digest"]
    same_code = manifest["snapshot"]["code_digest"] == baseline["snapshot"]["code_digest"]
    confounders: list[str] = []
    if not same_profile:
        confounders.append("profile changed")
    if not same_code:
        confounders.append("code snapshot changed")
    if manifest["prompt_digest"] != baseline["prompt_digest"]:
        confounders.append("audit prompt changed")
    for key in ("provider", "effort", "harness", "tools", "budget"):
        if manifest["reviewer"][key] != baseline["reviewer"][key]:
            confounders.append(f"{key} changed")
    return {
        "kind": "incompatible-profile"
        if not same_profile
        else "fixed-snapshot"
        if same_code
        else "rolling-code",
        "controlled_model_comparison": not confounders,
        "confounders": confounders,
        "model_changed": manifest["reviewer"]["model"] != baseline["reviewer"]["model"],
        "limitation": "Comparison controls are operator-declared; a single run does not establish model superiority.",
    }


def report(repo: Path, run_id: str) -> dict[str, Any]:
    """Read and revalidate retained evidence; never infer resolution from an omission."""
    repo = repo.resolve(strict=True)
    lineage = _lineage(repo, run_id)
    ledger: dict[str, dict[str, Any]] = {}
    for manifest, findings in lineage:
        current_keys: set[str] = set()
        for finding in findings:
            canonical = finding["canonical_key"]
            key = (
                f"{manifest['profile']['id']}:{canonical}"
                if canonical
                else f"unmatched:{manifest['run_id']}:{finding['fingerprint']}"
            )
            prior = ledger.get(key)
            if key in current_keys:
                raise ValueError(
                    "multiple findings share a canonical identity; adjudicate distinct mechanisms explicitly"
                )
            current_keys.add(key)
            verdict = finding["verdict"]
            was_verified = bool(prior and prior.get("last_verified_run_id"))
            status = (
                ("known" if was_verified else "newly_verified")
                if verdict == "verified"
                else verdict
            )
            ledger[key] = {
                **finding,
                "identity": key,
                "status": status,
                "resolved": False,
                "first_seen_run_id": prior["first_seen_run_id"] if prior else manifest["run_id"],
                "last_seen_run_id": manifest["run_id"],
                "last_verified_run_id": manifest["run_id"]
                if verdict == "verified"
                else prior.get("last_verified_run_id")
                if prior
                else None,
            }
        for key, item in ledger.items():
            if key not in current_keys:
                item["status"] = "not_reobserved"
    current = lineage[-1][0]
    baseline = lineage[-2][0] if len(lineage) > 1 else None
    findings = sorted(ledger.values(), key=lambda item: item["identity"])
    counts = Counter(item["status"] for item in findings)
    return {
        "schema": PREFIX + "report/v1",
        "status": "reported",
        "read_only": True,
        "implementation_allowed": False,
        "repo_root": str(repo),
        "run_id": run_id,
        "profile": current["profile"],
        "reviewer": current["reviewer"],
        "snapshot_digest": current["snapshot"]["code_digest"],
        "lineage": [manifest["run_id"] for manifest, _ in lineage],
        "comparison": _comparison(current, baseline),
        "counts": {status: counts[status] for status in STATUSES},
        "findings": findings,
        "current_workspace_freshness": "not checked; evidence is for the retained snapshot",
        "limitations": [
            "A missing finding remains unresolved, including across multiple refreshes.",
            "Verification is a separate attestation with digest-bound evidence, not independent proof of identity or behavior.",
            "Only selected tracked files were captured; provider isolation and actual effort are not verified.",
            "Remediation and accepted-risk decisions remain in the existing finding workflow.",
        ],
    }


def fleet_report(raw_selection: object) -> dict[str, Any]:
    """Aggregate explicit repo/run pairs without scanning, mutation, or implicit latest selection."""
    selection = object_value(raw_selection, "selection")
    exact_keys(selection, {"schema", "repositories"}, "selection")
    if selection["schema"] != PREFIX + "selection/v1":
        raise ValueError("unsupported model audit selection schema")
    repositories = array_value(selection["repositories"], "repositories", minimum=1)
    reports: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []
    seen: set[str] = set()
    patterns: dict[str, dict[str, Any]] = {}
    for raw_item in repositories:
        item = object_value(raw_item, "selection item")
        exact_keys(item, {"repo_path", "run_id"}, "selection item")
        root = Path(text(item["repo_path"], "repo_path"))
        if not root.is_absolute():
            raise ValueError("selection repo_path must be absolute")
        resolved = str(root.resolve())
        if resolved in seen:
            raise ValueError("selection contains duplicate repositories")
        seen.add(resolved)
        run_id = text(item["run_id"], "run_id")
        try:
            result = report(root, run_id)
        except (ValueError, OSError, KeyError, TypeError) as error:
            unavailable.append({"repo_path": str(root), "run_id": run_id, "error": str(error)})
            continue
        reports.append(result)
        criteria = {criterion["id"]: criterion for criterion in result["profile"]["criteria"]}
        for finding in result["findings"]:
            if finding["status"] not in {"newly_verified", "known"}:
                continue
            criterion = criteria[finding["criterion_id"]]
            pattern = patterns.setdefault(
                digest(criterion), {"criterion": criterion, "repositories": set()}
            )
            pattern["repositories"].add(str(root))
    return {
        "schema": PREFIX + "fleet/v1",
        "status": "partial" if unavailable else "reported",
        "read_only": True,
        "implementation_allowed": False,
        "coverage": {
            "selected": len(repositories),
            "reported": len(reports),
            "unavailable": len(unavailable),
        },
        "repositories": reports,
        "unavailable": unavailable,
        "recurring_criteria": [
            {
                "criterion": item["criterion"],
                "repositories": sorted(item["repositories"]),
                "interpretation": "Verified findings share a criterion; a shared root cause is not established.",
            }
            for _, item in sorted(patterns.items())
            if len(item["repositories"]) > 1
        ],
    }
