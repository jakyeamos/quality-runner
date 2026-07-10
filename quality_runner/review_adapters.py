from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, TypedDict

from quality_runner.review_report import build_review_report
from quality_runner.review_types import ReviewPacket

MAX_OUTPUT_BYTES = 2_000_000


class AdapterResult(TypedDict):
    status: str
    report: dict[str, object] | None
    evidence_unavailable: list[str]
    message: str | None


class ReviewAdapter(Protocol):
    def review(self, packet: ReviewPacket, output_dir: Path) -> AdapterResult: ...


class NoReviewAdapter:
    def review(self, packet: ReviewPacket, output_dir: Path) -> AdapterResult:
        return {
            "status": "review-not-run",
            "report": None,
            "evidence_unavailable": ["No review adapter was selected."],
            "message": "Provide --adapter-output with a local structured review result.",
        }


class FileReviewAdapter:
    def __init__(self, result_path: Path) -> None:
        self.result_path = result_path.expanduser().resolve()

    def review(self, packet: ReviewPacket, output_dir: Path) -> AdapterResult:
        approved_root = output_dir.expanduser().resolve()
        if not _within(self.result_path, approved_root):
            return _permission_result("Adapter output must remain inside the review artifact directory.")
        try:
            size = self.result_path.stat().st_size
            if size > MAX_OUTPUT_BYTES:
                return _malformed_result("Adapter output exceeds the local size limit.")
            raw = json.loads(self.result_path.read_text(encoding="utf-8"))
        except PermissionError:
            return _permission_result("Adapter output could not be read due to permissions.")
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            return _malformed_result(f"Adapter output is not readable JSON: {error}")
        if not isinstance(raw, Mapping):
            return _malformed_result("Adapter output must be a JSON object.")
        findings = raw.get("findings", [])
        if not isinstance(findings, list):
            return _malformed_result("Adapter output findings must be a list.")
        if not all(isinstance(item, Mapping) for item in findings):
            return _malformed_result("Adapter output findings must contain only JSON objects.")
        try:
            report = build_review_report(
                run_id=str(packet["run_id"]),
                mode=str(packet["mode"]),
                scope=str(packet["scope"]),
                breadth=str(packet["breadth"]),
                findings=list(findings),
                evidence_used=_strings(raw.get("evidence_used")),
                evidence_unavailable=_strings(raw.get("evidence_unavailable")),
                exclusions=_strings(packet.get("exclusions")),
                adapter_status="review-complete",
                task_provenance=str(packet.get("input_hashes", {}).get("task"))
                if packet.get("mode") != "blind"
                else None,
            )
        except (KeyError, TypeError, ValueError) as error:
            return _malformed_result(f"Adapter output failed review validation: {error}")
        return {"status": "review-complete", "report": report, "evidence_unavailable": [], "message": None}


def adapter_from_path(result_path: Path | None) -> ReviewAdapter:
    return FileReviewAdapter(result_path) if result_path is not None else NoReviewAdapter()


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _malformed_result(message: str) -> AdapterResult:
    return {"status": "malformed-output", "report": None, "evidence_unavailable": [message], "message": message}


def _permission_result(message: str) -> AdapterResult:
    return {"status": "permission-denied", "report": None, "evidence_unavailable": [message], "message": message}
