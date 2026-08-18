from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.fleet.audit import (
    fleet_audit_payload,
    fleet_replay_payload,
    fleet_report_payload,
    fleet_show_payload,
)
from quality_runner.fleet.contracts import SUPPORTED_FLEET_STANDARDS
from quality_runner.fleet.custody import custody_validation_payload
from quality_runner.fleet.detector_refresh import fleet_detector_refresh_payload
from quality_runner.fleet.feed import fleet_feed_payload
from quality_runner.fleet.mac_control import (
    mac_control_audit_payload,
    mac_control_feed_payload,
    mac_control_replay_payload,
    mac_control_report_payload,
)
from quality_runner.fleet.workspace_policy import fleet_workspace_target_payload


def add_fleet_commands(subparsers: Any) -> None:
    fleet_parser = subparsers.add_parser(
        "fleet",
        help="Run bounded fleet audits and explicit detector-evidence publication",
    )
    fleet_actions = fleet_parser.add_subparsers(dest="fleet_action", required=True)
    detector_parser = fleet_actions.add_parser(
        "detector", help="Refresh full detector evidence at exact repository targets"
    )
    detector_actions = detector_parser.add_subparsers(dest="detector_action", required=True)
    detector_refresh = detector_actions.add_parser(
        "refresh",
        help="Run full skill-pack scans in disposable worktrees and publish QR runs",
        description=(
            "Run full skill-pack scans at exact target commits in disposable worktrees, "
            "publish normal QR runs, and record blocked or unsupported repositories."
        ),
    )
    detector_refresh.add_argument("--all", action="store_true")
    detector_refresh.add_argument("--repo-path", action="append", default=[])
    detector_refresh.add_argument("--projects-root", default=str(Path.home() / "projects"))
    detector_refresh.add_argument("--output-dir", default=None)
    detector_refresh.add_argument("--timeout-seconds", type=int, default=600)
    detector_refresh.add_argument(
        "--anti-slop-root",
        default=None,
        help=(
            "Exact clean checkout of the pinned eslint-plugin-anti-slop source; "
            "when supplied, compatible JS/TS repositories receive the evidence detector"
        ),
    )
    detector_refresh.add_argument(
        "--anti-slop-preset",
        choices=("evidence",),
        default="evidence",
        help="Pinned Anti-Slop preset used by the external detector",
    )
    detector_refresh.add_argument(
        "--anti-slop-format",
        choices=("json", "sarif"),
        default="json",
        help="Machine-readable Anti-Slop output consumed by QR",
    )
    detector_refresh.add_argument(
        "--agent-review-mode", choices=("off", "auto", "parallel", "required"), default="off"
    )
    detector_refresh.add_argument(
        "--target-override",
        action="append",
        default=[],
        metavar="REPO_ID=BRANCH",
        help="Override the exact target by QR repository id",
    )
    detector_refresh.add_argument(
        "--target-path-override",
        action="append",
        nargs=2,
        default=[],
        metavar=("ABSOLUTE_PATH", "BRANCH"),
        help="Override the exact target by absolute primary path; repeat for orchestrators",
    )
    detector_refresh.add_argument("--as-of", default=None)
    detector_refresh.add_argument("--json", action="store_true")
    custody_parser = fleet_actions.add_parser(
        "custody",
        help="Validate isolated-change-workflow custody from independent live evidence",
    )
    custody_actions = custody_parser.add_subparsers(dest="custody_action", required=True)
    custody_validate = custody_actions.add_parser(
        "validate",
        help="Read-only custody validation; this command never grants mutation authority",
    )
    custody_validate.add_argument("repository", nargs="?", default=None)
    custody_validate.add_argument("--repo-path", default=None)
    custody_validate.add_argument("--stale-seconds", type=int, default=86400)
    custody_validate.add_argument("--adoptable-seconds", type=int, default=259200)
    custody_validate.add_argument("--as-of", default=None)
    custody_validate.add_argument(
        "--workspace-policy",
        default=None,
        help="Optional repository policy; defaults to .agents/workspace-policy.json when present",
    )
    custody_validate.add_argument("--json", action="store_true")
    target_parser = fleet_actions.add_parser(
        "workspace-target",
        help="Calculate role-based canonical workspace targets without mutation",
    )
    target_actions = target_parser.add_subparsers(dest="workspace_target_action", required=True)
    target_calculate = target_actions.add_parser(
        "calculate",
        help="Calculate 2P + 1N plus explicitly active temporary lanes",
    )
    target_calculate.add_argument("--manifest", required=True)
    target_calculate.add_argument("--as-of", default=None)
    target_calculate.add_argument("--json", action="store_true")
    audit_parser = fleet_actions.add_parser(
        "audit",
        help="Run, inspect, replay, or report a fleet environment-legibility audit",
    )
    audit_actions = audit_parser.add_subparsers(dest="audit_action", required=True)

    run_parser = audit_actions.add_parser(
        "run", help="Run static-all and optional dynamic fleet audit"
    )
    run_parser.add_argument(
        "--all", action="store_true", help="Audit every repository identity under the bounded root"
    )
    run_parser.add_argument(
        "--repo-path",
        action="append",
        default=[],
        help="Audit one explicit repository path under --projects-root; repeat for a bounded slice",
    )
    run_parser.add_argument(
        "--scope-manifest",
        default=None,
        help=(
            "Audit the exact eligible population in a quality-runner-fleet-scope/v1 manifest; "
            "mutually exclusive with --all and --repo-path"
        ),
    )
    run_parser.add_argument("--projects-root", default=str(Path.home() / "projects"))
    run_parser.add_argument(
        "--output-dir", default=None, help="Runtime-owned audit directory override"
    )
    run_parser.add_argument(
        "--standard",
        choices=SUPPORTED_FLEET_STANDARDS,
        default=None,
        help=(
            "Audit every selected repository against only one named standard; "
            "standard-scoped audits are static-only and do not publish the canonical feed"
        ),
    )
    run_parser.add_argument(
        "--dynamic", action="store_true", help="Run selected dynamic checks in disposable worktrees"
    )
    run_parser.add_argument(
        "--changed-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Select dynamic work only for changed, new, stale, failed, priority, or incomplete evidence",
    )
    run_parser.add_argument("--dynamic-max-age-days", type=int, default=30)
    run_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Cap each dynamic command; QR also derives a bounded per-repository watchdog",
    )
    run_parser.add_argument(
        "--target-override",
        action="append",
        default=[],
        metavar="REPO_ID=BRANCH",
        help="Override the documented development branch for one repository identity",
    )
    run_parser.add_argument(
        "--as-of", default=None, help="Fixed ISO-8601 timestamp for deterministic replay"
    )
    run_parser.add_argument(
        "--mac-control",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include the static Mac Control lane in the QR maturity checkpoint",
    )
    run_parser.add_argument(
        "--mac-control-live",
        action="store_true",
        help="Explicitly run live Mac Control foreground checks as part of this checkpoint",
    )
    run_parser.add_argument("--macctl", default="macctl")
    run_parser.add_argument(
        "--mac-control-evidence-dir",
        default=None,
        help="Directory of redacted Mac Control task evidence files named REPO_ID.json",
    )
    run_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    show_parser = audit_actions.add_parser(
        "show", help="Show one private repository finding and plan"
    )
    show_parser.add_argument("--repo-id", required=True)
    show_parser.add_argument("--audit-id", default=None)
    show_parser.add_argument("--output-dir", default=None)
    show_parser.add_argument("--json", action="store_true")

    replay_parser = audit_actions.add_parser(
        "replay", help="Replay a persisted fleet audit deterministically"
    )
    replay_parser.add_argument("--audit-id", default=None)
    replay_parser.add_argument("--output-dir", default=None)
    replay_parser.add_argument("--json", action="store_true")

    report_parser = audit_actions.add_parser(
        "report", help="Render an aggregate-only reviewable report"
    )
    report_parser.add_argument("--audit-id", default=None)
    report_parser.add_argument("--output-dir", default=None)
    report_parser.add_argument("--json", action="store_true")

    feed_parser = audit_actions.add_parser(
        "feed", help="Validate and publish one fleet audit as the stable maturity feed"
    )
    feed_parser.add_argument("--audit-id", default=None)
    feed_parser.add_argument("--output-dir", default=None)
    feed_parser.add_argument(
        "--allow-incomplete-coverage",
        action="store_true",
        help=(
            "Publish a diagnostic feed when unfolded or ambiguous work makes repository "
            "comparisons ineligible"
        ),
    )
    feed_parser.add_argument("--json", action="store_true")

    mac_control_parser = fleet_actions.add_parser(
        "mac-control",
        help="Audit the explicit Mac Control ideal-state lane without changing repository checkouts",
    )
    mac_control_actions = mac_control_parser.add_subparsers(
        dest="mac_control_action", required=True
    )
    mac_control_audit_parser = mac_control_actions.add_parser(
        "audit", help="Run, replay, report, or publish the Mac Control ideal-state audit"
    )
    mac_control_audit_actions = mac_control_audit_parser.add_subparsers(
        dest="mac_control_audit_action", required=True
    )
    mc_run_parser = mac_control_audit_actions.add_parser(
        "run", help="Validate repository-owned manifests and optional live Mac Control evidence"
    )
    mc_run_parser.add_argument("--all", action="store_true")
    mc_run_parser.add_argument("--repo-path", action="append", default=[])
    mc_run_parser.add_argument("--projects-root", default=str(Path.home() / "projects"))
    mc_run_parser.add_argument("--output-dir", default=None)
    mc_run_parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly call Mac Control for live foreground Accessibility audits; never implicit",
    )
    mc_run_parser.add_argument("--macctl", default="macctl")
    mc_run_parser.add_argument(
        "--evidence-dir",
        default=None,
        help="Directory of redacted Mac Control task evidence files named REPO_ID.json",
    )
    mc_run_parser.add_argument("--as-of", default=None)
    mc_run_parser.add_argument("--json", action="store_true")
    for action, help_text in (
        ("replay", "Replay a persisted Mac Control audit without rerunning GUI work"),
        ("report", "Render the persisted Mac Control report for review"),
        ("feed", "Publish the validated Mac Control companion report for Pronto"),
    ):
        parser = mac_control_audit_actions.add_parser(action, help=help_text)
        parser.add_argument("--audit-id", default=None)
        parser.add_argument("--output-dir", default=None)
        parser.add_argument("--json", action="store_true")


def fleet_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.fleet_action == "workspace-target":
        if args.workspace_target_action != "calculate":
            raise ValueError(
                f"unsupported fleet workspace-target action: {args.workspace_target_action}"
            )
        return fleet_workspace_target_payload(Path(args.manifest), as_of=args.as_of)
    if args.fleet_action == "custody":
        if args.custody_action != "validate":
            raise ValueError(f"unsupported fleet custody action: {args.custody_action}")
        if bool(args.repository) == bool(args.repo_path):
            raise ValueError("fleet custody validate requires exactly one repository path")
        return custody_validation_payload(
            Path(args.repository or args.repo_path),
            stale_seconds=args.stale_seconds,
            adoptable_seconds=args.adoptable_seconds,
            as_of=args.as_of,
            workspace_policy_path=(Path(args.workspace_policy) if args.workspace_policy else None),
        )
    if args.fleet_action == "mac-control":
        if args.mac_control_action != "audit":
            raise ValueError(f"unsupported Mac Control action: {args.mac_control_action}")
        action = args.mac_control_audit_action
        if action == "run":
            if not args.all and not args.repo_path:
                raise ValueError(
                    "fleet mac-control audit run requires --all or at least one --repo-path"
                )
            if args.all and args.repo_path:
                raise ValueError(
                    "fleet mac-control audit run accepts --all or --repo-path, not both"
                )
            return mac_control_audit_payload(
                projects_root=Path(args.projects_root),
                output_dir=Path(args.output_dir) if args.output_dir else None,
                repository_paths=[Path(path) for path in args.repo_path]
                if args.repo_path
                else None,
                as_of=args.as_of,
                live=args.live,
                macctl_path=args.macctl,
                evidence_dir=Path(args.evidence_dir) if args.evidence_dir else None,
            )
        if action == "replay":
            return mac_control_replay_payload(
                audit_id=args.audit_id,
                output_dir=Path(args.output_dir) if args.output_dir else None,
            )
        if action == "report":
            return mac_control_report_payload(
                audit_id=args.audit_id,
                output_dir=Path(args.output_dir) if args.output_dir else None,
            )
        if action == "feed":
            return mac_control_feed_payload(
                audit_id=args.audit_id,
                output_dir=Path(args.output_dir) if args.output_dir else None,
            )
        raise ValueError(f"unsupported Mac Control audit action: {action}")
    if args.fleet_action == "detector":
        if args.detector_action != "refresh":
            raise ValueError(f"unsupported fleet detector action: {args.detector_action}")
        if not args.all and not args.repo_path:
            raise ValueError("fleet detector refresh requires --all or at least one --repo-path")
        if args.all and args.repo_path:
            raise ValueError("fleet detector refresh accepts --all or --repo-path, not both")
        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be positive")
        return fleet_detector_refresh_payload(
            projects_root=Path(args.projects_root),
            output_dir=Path(args.output_dir) if args.output_dir else None,
            repository_paths=[Path(path) for path in args.repo_path] if args.repo_path else None,
            target_overrides={
                **_target_overrides(args.target_override),
                **_target_path_overrides(args.target_path_override),
            },
            timeout_seconds=args.timeout_seconds,
            agent_review_mode=args.agent_review_mode,
            as_of=args.as_of,
            anti_slop_root=Path(args.anti_slop_root) if args.anti_slop_root else None,
            anti_slop_preset=args.anti_slop_preset,
            anti_slop_format=args.anti_slop_format,
        )
    if args.fleet_action != "audit":
        raise ValueError(f"unsupported fleet action: {args.fleet_action}")
    if args.audit_action == "run":
        scope_selectors = int(args.all) + int(bool(args.repo_path)) + int(bool(args.scope_manifest))
        if scope_selectors != 1:
            raise ValueError(
                "fleet audit run requires exactly one of --all, --repo-path, or --scope-manifest"
            )
        return fleet_audit_payload(
            projects_root=Path(args.projects_root),
            output_dir=Path(args.output_dir) if args.output_dir else None,
            dynamic=args.dynamic,
            changed_only=args.changed_only,
            dynamic_max_age_days=args.dynamic_max_age_days,
            timeout_seconds=args.timeout_seconds,
            target_overrides=_target_overrides(args.target_override),
            repository_paths=[Path(path) for path in args.repo_path] if args.repo_path else None,
            as_of=args.as_of,
            standard=args.standard,
            scope_manifest=Path(args.scope_manifest) if args.scope_manifest else None,
            mac_control=args.mac_control,
            mac_control_live=args.mac_control_live,
            macctl_path=args.macctl,
            mac_control_evidence_dir=(
                Path(args.mac_control_evidence_dir) if args.mac_control_evidence_dir else None
            ),
        )
    if args.audit_action == "show":
        return fleet_show_payload(
            repo_id=args.repo_id,
            audit_id=args.audit_id,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    if args.audit_action == "replay":
        return fleet_replay_payload(
            audit_id=args.audit_id,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    if args.audit_action == "report":
        return fleet_report_payload(
            audit_id=args.audit_id,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    if args.audit_action == "feed":
        return fleet_feed_payload(
            audit_id=args.audit_id,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            allow_incomplete_coverage=args.allow_incomplete_coverage,
        )
    raise ValueError(f"unsupported fleet audit action: {args.audit_action}")


def _target_overrides(values: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--target-override must use REPO_ID=BRANCH")
        repo_id, branch = value.split("=", maxsplit=1)
        if not repo_id or not branch:
            raise ValueError("--target-override must include both repository id and branch")
        overrides[repo_id] = branch
    return overrides


def _target_path_overrides(values: list[list[str]]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for path, branch in values:
        primary_path = str(Path(path).expanduser().resolve())
        if not branch:
            raise ValueError("--target-path-override must include a branch")
        overrides[primary_path] = branch
    return overrides
