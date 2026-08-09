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
from quality_runner.fleet.feed import fleet_feed_payload
from quality_runner.fleet.mac_control import (
    mac_control_audit_payload,
    mac_control_feed_payload,
    mac_control_replay_payload,
    mac_control_report_payload,
)


def add_fleet_commands(subparsers: Any) -> None:
    fleet_parser = subparsers.add_parser(
        "fleet",
        help="Run bounded fleet audits without modifying repository checkouts",
    )
    fleet_actions = fleet_parser.add_subparsers(dest="fleet_action", required=True)
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
    run_parser.add_argument("--projects-root", default=str(Path.home() / "projects"))
    run_parser.add_argument(
        "--output-dir", default=None, help="Runtime-owned audit directory override"
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
    run_parser.add_argument("--timeout-seconds", type=int, default=120)
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
    if args.fleet_action != "audit":
        raise ValueError(f"unsupported fleet action: {args.fleet_action}")
    if args.audit_action == "run":
        if not args.all and not args.repo_path:
            raise ValueError("fleet audit run requires --all or at least one --repo-path")
        if args.all and args.repo_path:
            raise ValueError("fleet audit run accepts --all or --repo-path, not both")
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
