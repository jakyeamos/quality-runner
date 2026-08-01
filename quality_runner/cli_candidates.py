from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.bug_learning import (
    CANDIDATE_REGISTRY_FILE,
    aggregate_candidate_fleet,
    check_candidate_promotion,
    validate_candidate_registry,
)


def add_candidate_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "candidates",
        help="Validate bug lessons, aggregate fleet observations, and check promotions",
    )
    actions = parser.add_subparsers(dest="candidate_action", required=True)

    validate = actions.add_parser(
        "validate",
        help="Check that every declared regression has a governed candidate disposition",
    )
    validate.add_argument("repo_path", help="Target repository path")
    validate.add_argument(
        "--registry",
        default=CANDIDATE_REGISTRY_FILE,
        help="Repository-relative candidate registry path",
    )
    validate.add_argument("--json", action="store_true")

    aggregate = actions.add_parser(
        "aggregate",
        help="Aggregate candidate occurrences and durable observation history",
    )
    aggregate.add_argument("--projects-root", required=True)
    aggregate.add_argument(
        "--output",
        required=True,
        help="Private candidate-fleet JSON artifact path",
    )
    aggregate.add_argument("--as-of", default=None)
    aggregate.add_argument("--json", action="store_true")

    promotion = actions.add_parser(
        "promotion-check",
        help="Fail closed unless fleet criteria and a human approval support required promotion",
    )
    promotion.add_argument("repo_path", help="Target repository path")
    promotion.add_argument("--candidate-id", required=True)
    promotion.add_argument("--fleet-evidence", required=True)
    promotion.add_argument("--decision", required=True)
    promotion.add_argument(
        "--output",
        required=True,
        help="Repository-owned promotion receipt JSON path",
    )
    promotion.add_argument(
        "--registry",
        default=CANDIDATE_REGISTRY_FILE,
        help="Repository-relative candidate registry path",
    )
    promotion.add_argument("--json", action="store_true")


def candidate_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.candidate_action == "validate":
        return validate_candidate_registry(
            Path(args.repo_path),
            registry_path=args.registry,
        )
    if args.candidate_action == "aggregate":
        return aggregate_candidate_fleet(
            projects_root=Path(args.projects_root),
            output_path=Path(args.output),
            as_of=args.as_of,
        )
    if args.candidate_action == "promotion-check":
        return check_candidate_promotion(
            repo_root=Path(args.repo_path),
            candidate_id=args.candidate_id,
            fleet_evidence_path=Path(args.fleet_evidence),
            decision_path=Path(args.decision),
            registry_path=args.registry,
            output_path=Path(args.output),
        )
    raise ValueError(f"unsupported candidate action: {args.candidate_action}")
