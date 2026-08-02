"""CLI routing for the coverage-aware Codex Security evidence workflow."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.security.codex import (
    compare_codex_evidence,
    export_codex_handoff,
    import_codex_evidence,
    load_codex_json,
    render_codex_handoff_markdown,
    security_result,
    validate_codex_document,
    write_codex_json,
)


def add_security_commands(
    subparsers: Any,
) -> None:
    security = subparsers.add_parser(
        "security",
        help="Import and compare coverage-aware security evidence",
    )
    actions = security.add_subparsers(dest="security_action", required=True)

    import_parser = actions.add_parser(
        "import-codex",
        help="Normalize a Codex Security or SARIF report into QR evidence",
    )
    _add_single_input(import_parser, "Codex Security report JSON")
    _add_output(import_parser)
    import_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    validate_parser = actions.add_parser(
        "validate",
        help="Validate a normalized security evidence, comparison, or handoff artifact",
    )
    _add_single_input(validate_parser, "Security artifact JSON")
    validate_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    compare_parser = actions.add_parser(
        "compare",
        help="Compare baseline and follow-up evidence with coverage-aware disappearance",
    )
    compare_parser.add_argument("baseline_path", nargs="?", help="Baseline evidence JSON")
    compare_parser.add_argument("current_path", nargs="?", help="Follow-up evidence JSON")
    compare_parser.add_argument("--baseline", dest="baseline_option", help="Baseline evidence JSON")
    compare_parser.add_argument("--current", dest="current_option", help="Follow-up evidence JSON")
    compare_parser.add_argument(
        "--follow-up",
        dest="follow_up_option",
        default=None,
        help="Optional coverage JSON to bind to the follow-up scan",
    )
    _add_output(compare_parser)
    compare_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    export_parser = actions.add_parser(
        "export",
        help="Export a hash-bound comparison handoff",
    )
    export_parser.add_argument("comparison_path", nargs="?", help="Comparison JSON")
    export_parser.add_argument("--comparison", dest="comparison_option", help="Comparison JSON")
    export_parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Artifact format written to --output (default: json)",
    )
    _add_output(export_parser)
    export_parser.add_argument("--json", action="store_true", help="Emit JSON output")


def security_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.command != "security":
        raise ValueError(f"unsupported security command: {args.command}")
    if args.security_action == "import-codex":
        source_path = _required_path(args.input_path, args.input_option, "Codex Security report")
        artifact = import_codex_evidence(load_codex_json(source_path))
        output_path = _write_artifact(args.output, artifact)
        return security_result(
            operation="import-codex",
            status="imported",
            artifact=artifact,
            input_path=str(source_path),
            output_path=str(output_path) if output_path else None,
        )
    if args.security_action == "validate":
        input_path = _required_path(args.input_path, args.input_option, "Security artifact")
        artifact = load_codex_json(input_path)
        validation = validate_codex_document(artifact)
        validation_details = {
            key: value
            for key, value in validation.items()
            if key not in {"schema", "operation", "status", "implementation_allowed"}
        }
        return security_result(
            operation="validate",
            status=validation["status"],
            artifact=artifact if validation["passed"] else None,
            input_path=str(input_path),
            **validation_details,
        )
    if args.security_action == "compare":
        baseline_path = _required_path(
            args.baseline_path, args.baseline_option, "baseline evidence"
        )
        current_path = _required_path(args.current_path, args.current_option, "current evidence")
        follow_up = (
            load_codex_json(Path(args.follow_up_option).expanduser().resolve())
            if args.follow_up_option
            else None
        )
        comparison = compare_codex_evidence(
            load_codex_json(baseline_path),
            load_codex_json(current_path),
            follow_up_coverage=follow_up,
        )
        output_path = _write_artifact(args.output, comparison)
        return security_result(
            operation="compare",
            status="compared",
            artifact=comparison,
            baseline_path=str(baseline_path),
            current_path=str(current_path),
            output_path=str(output_path) if output_path else None,
        )
    if args.security_action == "export":
        comparison_path = _required_path(
            args.comparison_path, args.comparison_option, "comparison artifact"
        )
        comparison = load_codex_json(comparison_path)
        handoff = export_codex_handoff(comparison)
        output_path = _write_export(args.output, args.format, handoff)
        return security_result(
            operation="export",
            status="exported",
            artifact=handoff,
            comparison_path=str(comparison_path),
            output_path=str(output_path) if output_path else None,
        )
    raise ValueError(f"unsupported security action: {args.security_action}")


def _add_single_input(parser: argparse.ArgumentParser, help_text: str) -> None:
    parser.add_argument("input_path", nargs="?", help=help_text)
    parser.add_argument("--input", dest="input_option", help=help_text)


def _add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output", "--out", dest="output", default=None, help="Write artifact JSON"
    )


def _required_path(positional: str | None, option: str | None, label: str) -> Path:
    value = option or positional
    if not value:
        raise ValueError(f"{label} path is required")
    return Path(value).expanduser().resolve()


def _write_artifact(value: str | None, artifact: dict[str, Any]) -> Path | None:
    if not value:
        return None
    return write_codex_json(Path(value), artifact)


def _write_export(value: str | None, format_name: str, handoff: dict[str, Any]) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    if format_name == "markdown":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_codex_handoff_markdown(handoff), encoding="utf-8")
        return path
    return write_codex_json(path, handoff)


__all__ = ["add_security_commands", "security_command_payload"]
