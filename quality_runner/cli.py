from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from quality_runner import __version__
from quality_runner.cli_artifacts import add_artifact_commands
from quality_runner.cli_controller_reports import (
    add_controller_report_command,
    add_controller_report_summary_arguments,
    has_rejected_self_check,
)
from quality_runner.cli_fix_proposals import add_fix_proposal_command
from quality_runner.cli_gate import add_gate_commands
from quality_runner.cli_handoff import add_handoff_commands
from quality_runner.cli_human_summary import human_summary
from quality_runner.cli_journeys import add_journey_commands
from quality_runner.cli_outcome import OUTCOME_SCHEMA, render_outcome
from quality_runner.cli_payload import payload_for_args
from quality_runner.cli_phase import add_phase_commands
from quality_runner.cli_planning import add_planning_commands
from quality_runner.cli_remediation import add_remediation_commands
from quality_runner.cli_review import add_review_command
from quality_runner.cli_rollout import add_rollout_command
from quality_runner.cli_skills import add_skill_commands
from quality_runner.cli_update import add_update_command
from quality_runner.cli_workflow_args import (
    add_verify_arguments,
    add_workflow_arguments,
    add_worktree_verify_arguments,
)
from quality_runner.core.outcome_contracts import JourneyOutcome
from quality_runner.progress import ProgressReporter
from quality_runner.standards import DEFAULT_PROFILE

CANONICAL_PROGRAM = "qr"
COMPATIBILITY_PROGRAM = "quality-runner"


def _root_help(program_name: str) -> str:
    return f"""usage: {program_name} <journey> [options]

Quality Runner records local evidence and the safest next action for a repository.
The canonical command is 'qr'; 'quality-runner' remains a compatibility alias.

Stable journeys:
  audit REPO            inspect a repository and prepare remediation evidence
  review REPO           prepare or run a fresh, read-only review (v2 outcome)
  verify REPO           record gate evidence; execution requires explicit consent
  runs REPO             read recent evidence without creating new artifacts
  doctor                confirm local installation readiness

Configuration:
  init REPO             create a starter Quality Runner configuration

Compatibility commands remain available:
  inspect, run, verify-gates, status, summarize-run, export-handoff

Advanced operations:
  refresh, rollout, gate, controller-report, skill, proposal, remediation,
  plan, phase, release-smoke, and worker handoff tools

Run '{program_name} <command> --help' for options. Audit, review, verify, and
runs emit a compact outcome card by default and v2 JSON with --json. Use
review --legacy-output only for the supported v1 compatibility projection.
"""


ROOT_HELP = _root_help(CANONICAL_PROGRAM)

_LEGACY_COMMAND_REPLACEMENTS = {
    "inspect": "audit --inspect-only",
    "run": "audit",
    "verify-gates": "verify",
}
_PROGRESS_COMMANDS = {"run", "inspect", "verify-gates", "refresh", "release-smoke"}


def build_parser(prog: str = CANONICAL_PROGRAM) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Audit a repo and produce an evidence-backed remediation plan.",
    )

    def format_root_help() -> str:
        return ROOT_HELP if prog == CANONICAL_PROGRAM else _root_help(prog)

    parser.format_help = format_root_help
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")

    add_journey_commands(subparsers)

    run_parser = subparsers.add_parser("run", help="Inspect a repo and write audit artifacts")
    add_workflow_arguments(run_parser)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a repo without audit planning")
    add_workflow_arguments(inspect_parser)

    verify_parser = subparsers.add_parser(
        "verify-gates", help="Record discovered gates and optionally execute them"
    )
    add_workflow_arguments(verify_parser)
    add_verify_arguments(verify_parser)

    refresh_parser = subparsers.add_parser(
        "refresh",
        help="Run inspect, run, verify-gates, summarize, and optionally export a handoff",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Use --handoff-output to write a remediation handoff in the same command.\n\n"
            "Refresh emits gate handoff statuses for controller routing:\n"
            "  gates-clean    all discovered local gates passed\n"
            "  gates-blocked  execution consent, environment, dependency setup, or read-only policy blocked evidence\n"
            "  gates-failed   executable repo gates ran and failed\n\n"
            "Blocked and failed handoffs include gate_verification.blocker_groups and\n"
            "next_slice.action_groups. Use --total-timeout-reason to record why a\n"
            "full refresh deadline was applied when --total-timeout-seconds is set."
        ),
    )
    add_workflow_arguments(refresh_parser)
    refresh_parser.add_argument(
        "--run-id-prefix",
        required=True,
        help="Prefix used to create <prefix>-inspect, <prefix>-run, and <prefix>-verify runs",
    )
    refresh_parser.add_argument(
        "--baseline-run-id", default=None, help="Baseline run id for deltas"
    )
    refresh_parser.add_argument(
        "--review-cycle-id",
        default=None,
        help="Stable task implement-review cycle id; enables review-delta artifacts",
    )
    refresh_parser.add_argument(
        "--review-iteration",
        type=int,
        default=None,
        help="1-based iteration number within --review-cycle-id",
    )
    refresh_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Per-gate command timeout",
    )
    refresh_parser.add_argument(
        "--workflow-timeout-seconds",
        type=int,
        default=None,
        help=(
            "Backward-compatible alias for --verify-timeout-seconds; "
            "applies only to the verify-gates phase"
        ),
    )
    refresh_parser.add_argument(
        "--verify-timeout-seconds",
        type=int,
        default=None,
        help="Verify-gates phase timeout; defaults to a multiple of --timeout-seconds",
    )
    refresh_parser.add_argument(
        "--inspect-timeout-seconds",
        type=int,
        default=None,
        help="Explicit inspect phase timeout; otherwise uses the active adaptive budget or fallback",
    )
    refresh_parser.add_argument(
        "--run-timeout-seconds",
        type=int,
        default=None,
        help="Explicit run phase timeout; otherwise uses the active adaptive budget or fallback",
    )
    refresh_parser.add_argument(
        "--workflow-timeout-reason",
        default=None,
        help="Reason recorded when the verify-gates timeout fires",
    )
    refresh_parser.add_argument(
        "--total-timeout-seconds",
        type=int,
        default=None,
        help="Optional hard deadline for the full refresh across inspect, run, and verify",
    )
    refresh_parser.add_argument(
        "--total-timeout-reason",
        default=None,
        help="Reason recorded when the total refresh timeout fires",
    )
    refresh_parser.add_argument(
        "--allow-mutating-gates",
        action="store_true",
        help="Allow known or suspected mutating gates to execute during refresh",
    )
    refresh_parser.add_argument(
        "--execute-gates",
        action="store_true",
        help="Execute discovered repository commands in a disposable worktree during refresh",
    )
    refresh_parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Limit inspect/run analysis to paths changed from the baseline and working tree",
    )
    add_worktree_verify_arguments(refresh_parser)
    refresh_parser.add_argument(
        "--handoff-output",
        default=None,
        help="Write the generated remediation handoff markdown to this path",
    )

    add_rollout_command(subparsers)
    add_review_command(subparsers)

    exclusions_parser = subparsers.add_parser(
        "exclusions",
        help="Inventory and review repository scan-exclusion candidates",
    )
    exclusion_actions = exclusions_parser.add_subparsers(
        dest="exclusions_action",
        required=True,
    )
    suggest_exclusions_parser = exclusion_actions.add_parser(
        "suggest",
        help="Write a deterministic review packet without changing repo config",
    )
    suggest_exclusions_parser.add_argument("repo_path", help="Target repository path")
    suggest_exclusions_parser.add_argument("--run-id", default=None, help="Stable run id")
    suggest_exclusions_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    suggest_exclusions_parser.set_defaults(apply=False)

    for action_name, action_help in (
        ("validate", "Validate a supervising-agent report without changing repo config"),
        ("apply", "Apply validated exclude decisions to repo config"),
    ):
        action_parser = exclusion_actions.add_parser(action_name, help=action_help)
        action_parser.add_argument("repo_path", help="Target repository path")
        action_parser.add_argument("--packet", required=True, help="Preflight packet JSON path")
        action_parser.add_argument("--report", required=True, help="Agent report JSON path")
        action_parser.add_argument("--run-id", default=None, help="Stable run id")
        if action_name == "apply":
            action_parser.add_argument(
                "--apply",
                action="store_true",
                help="Explicitly authorize the .quality-runner.toml mutation",
            )
        else:
            action_parser.set_defaults(apply=False)
        action_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    init_parser = subparsers.add_parser("init", help="Write a starter .quality-runner.toml")
    init_parser.add_argument("repo_path", help="Target repository path")
    init_parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Default standards profile")
    init_parser.add_argument(
        "--required-capability",
        action="append",
        default=[],
        help="Required capability to add to the starter config",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite an existing config")
    init_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    status_parser = subparsers.add_parser("status", help="Show repo Quality Runner state")
    status_parser.add_argument("repo_path", help="Target repository path")
    status_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    summary_parser = subparsers.add_parser(
        "summarize-run", help="Summarize a Quality Runner run and optional baseline delta"
    )
    summary_parser.add_argument("repo_path", help="Target repository path")
    summary_parser.add_argument("--run-id", required=True, help="Run id to summarize")
    summary_parser.add_argument(
        "--baseline-run-id", default=None, help="Baseline run id for deltas"
    )
    add_controller_report_summary_arguments(summary_parser)
    summary_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    export_parser = subparsers.add_parser("export-handoff", help="Print or write an agent handoff")
    export_parser.add_argument("repo_path", help="Target repository path")
    export_parser.add_argument("--run-id", default=None, help="Run id to export")
    export_parser.add_argument("--output", default=None, help="Write handoff markdown to this path")
    export_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    validate_report_parser = subparsers.add_parser(
        "validate-report", help="Validate a controller thread completion report"
    )
    validate_report_parser.add_argument("report_json", help="Controller report JSON path")
    validate_report_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    add_controller_report_command(subparsers)

    add_skill_commands(subparsers)

    add_gate_commands(subparsers)

    add_fix_proposal_command(subparsers)

    add_artifact_commands(subparsers)

    add_handoff_commands(subparsers)

    add_remediation_commands(subparsers)

    add_planning_commands(subparsers)
    add_phase_commands(subparsers)

    doctor_parser = subparsers.add_parser("doctor", help="Check Quality Runner readiness")
    doctor_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    add_update_command(subparsers)

    release_smoke_parser = subparsers.add_parser(
        "release-smoke",
        help="Run pre-release CLI, refresh, handoff, and schema smoke checks",
    )
    release_smoke_parser.add_argument(
        "--work-dir",
        default=None,
        help="Directory for temporary release-smoke repo and handoff outputs",
    )
    release_smoke_parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable stderr progress and heartbeat diagnostics",
    )
    release_smoke_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    program_name = _program_for_invocation()
    if not args:
        print(f"Quality Runner {__version__}")
        print(f"Run '{program_name} --help' for usage.")
        return 0

    parser = build_parser(program_name)
    payload: dict[str, Any] = {}
    try:
        parsed = parser.parse_args(args)
    except SystemExit as error:
        code = error.code
        return code if isinstance(code, int) else 2

    try:
        if parsed.command in _PROGRESS_COMMANDS and not getattr(parsed, "no_progress", False):
            with ProgressReporter(parsed.command, stream=sys.stderr) as progress:
                payload = payload_for_args(parsed, progress=progress.phase)
                progress.finish(str(payload.get("status", "completed")))
        else:
            payload = payload_for_args(parsed)
    except (FileNotFoundError, NotADirectoryError, ValueError, OSError) as error:
        print(f"{program_name}: error: {error}", file=sys.stderr)
        return 1

    notice = _compatibility_notice(parsed, program_name=program_name)
    if notice:
        print(notice, file=sys.stderr)

    if parsed.command == "export-handoff" and not getattr(parsed, "json", False):
        content = payload.get("content")
        if isinstance(content, str):
            print(content, end="" if content.endswith("\n") else "\n")
        else:
            print(human_summary(payload))
    elif getattr(parsed, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif payload.get("schema") == OUTCOME_SCHEMA:
        print(render_outcome(cast(JourneyOutcome, payload)))
    else:
        print(human_summary(payload))
    if (
        parsed.command
        in {
            "validate-report",
            "controller-report",
            "validate-skill-review",
            "validate-handoff",
            "validate-remediation-context",
            "validate-slice-spec",
            "review-worker",
            "phase-check",
            "exclusions",
        }
        and payload.get("status") == "rejected"
    ):
        return 1
    if parsed.command == "skill" and payload.get("status") == "rejected":
        return 1
    if parsed.command == "release-smoke" and payload.get("status") != "passed":
        return 1
    if parsed.command == "summarize-run" and has_rejected_self_check(payload):
        return 1
    if parsed.command == "phase-check" and payload.get("status") != "passed":
        return 1
    if parsed.command == "self-update" and payload.get("status") in {"blocked", "failed"}:
        return 1
    if parsed.command == "plan" and payload.get("status") == "blocked":
        return 1
    return 0


def _program_for_invocation(argv0: str | None = None) -> str:
    invoked_name = Path(argv0 or sys.argv[0]).name.removesuffix(".exe")
    if invoked_name == COMPATIBILITY_PROGRAM:
        return COMPATIBILITY_PROGRAM
    return CANONICAL_PROGRAM


def _compatibility_notice(
    parsed: argparse.Namespace, *, program_name: str = CANONICAL_PROGRAM
) -> str | None:
    command = parsed.command
    if not isinstance(command, str):
        return None
    if command == "review" and bool(getattr(parsed, "legacy_output", False)):
        return (
            f"{program_name}: warning: --legacy-output emits the v1 review projection, "
            "supported through 0.7.x; omit it for the v2 outcome."
        )
    replacement = _LEGACY_COMMAND_REPLACEMENTS.get(command)
    if replacement is None:
        return None
    return (
        f"{program_name}: warning: {command} is a v1 compatibility command, "
        f"supported through 0.7.x; use {replacement}."
    )


if __name__ == "__main__":
    raise SystemExit(main())
