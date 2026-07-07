from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.config import load_repo_config
from quality_runner.skill_config import load_active_skills
from quality_runner.skill_ingest import ingest_skill_pack
from quality_runner.skill_review import validate_skill_review_report
from quality_runner.workflow_skills import load_skill_review_report_json


def add_skill_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    skill_parser = subparsers.add_parser("skill", help="Quality Skill management")
    skill_subparsers = skill_parser.add_subparsers(dest="skill_command")

    skill_ingest_parser = skill_subparsers.add_parser(
        "ingest", help="Validate and optionally register a candidate skill pack"
    )
    skill_ingest_parser.add_argument("candidate_toml", help="Candidate skill TOML path")
    skill_ingest_parser.add_argument("--repo-path", required=True, help="Target repository path")
    skill_ingest_parser.add_argument("--id", required=True, dest="skill_id", help="Skill id")
    skill_ingest_parser.add_argument(
        "--activate", action="store_true", help="Activate the skill in .quality-runner.toml"
    )
    skill_ingest_parser.add_argument(
        "--write", action="store_true", help="Write skill pack and update repo config"
    )
    skill_ingest_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    validate_skill_review_parser = subparsers.add_parser(
        "validate-skill-review",
        help="Validate an agent-produced skill review report",
    )
    validate_skill_review_parser.add_argument("report_json", help="Skill review report JSON path")
    validate_skill_review_parser.add_argument(
        "--repo-path", default=None, help="Optional repo path for file containment checks"
    )
    validate_skill_review_parser.add_argument(
        "--json", action="store_true", help="Emit JSON output"
    )


def skill_command_payload(
    args: argparse.Namespace,
    *,
    validated_repo_path: Any,
) -> dict[str, Any]:
    if args.command == "validate-skill-review":
        report = load_skill_review_report_json(Path(args.report_json))
        repo_root = (
            validated_repo_path(args.repo_path) if getattr(args, "repo_path", None) else None
        )
        skills = load_active_skills(repo_root, load_repo_config(repo_root))[0] if repo_root else []
        return validate_skill_review_report(report, skills=skills, repo_root=repo_root)
    if args.command == "skill" and args.skill_command == "ingest":
        return ingest_skill_pack(
            Path(args.candidate_toml).expanduser().resolve(),
            skill_id=args.skill_id,
            repo_root=validated_repo_path(args.repo_path),
            activate=args.activate,
            write=args.write,
        )
    raise ValueError("unsupported skill command")
