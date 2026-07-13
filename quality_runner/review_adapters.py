from __future__ import annotations

from pathlib import Path
from typing import Protocol

from quality_runner.application.review_responses import validate_review_response
from quality_runner.core.review_contracts import AdapterResult, ReviewPacket
from quality_runner.core.review_packets import MAX_REVIEW_RESPONSE_BYTES
from quality_runner.review_response_files import (
    ReviewAdapterResponseError,
    ReviewAdapterResponsePermissionError,
    read_local_adapter_response,
)


class ReviewAdapter(Protocol):
    def review(self, packet: ReviewPacket, output_dir: Path) -> AdapterResult: ...


class NoReviewAdapter:
    """Packet preparation remains valid when no local reviewer response is configured."""

    def review(self, packet: ReviewPacket, output_dir: Path) -> AdapterResult:
        return {
            "status": "review-not-run",
            "report": None,
            "evidence_unavailable": ["No review adapter was selected."],
            "message": "Provide --adapter-output with a local structured review result.",
        }


class FileReviewAdapter:
    """Consume a strict local response bound to one prepared review packet."""

    def __init__(self, result_path: Path) -> None:
        self.result_path = result_path.expanduser()

    def review(self, packet: ReviewPacket, output_dir: Path) -> AdapterResult:
        root = output_dir.expanduser().resolve()
        candidate = self.result_path if self.result_path.is_absolute() else root / self.result_path
        try:
            raw = read_local_adapter_response(
                allowed_directory=root,
                response_path=candidate,
                relative_root=root,
                maximum_bytes=MAX_REVIEW_RESPONSE_BYTES,
            )
        except ReviewAdapterResponsePermissionError as error:
            return _permission_result(str(error))
        except ReviewAdapterResponseError as error:
            return _malformed_result(str(error))
        try:
            report, _ = validate_review_response(raw, packet)
        except (KeyError, ValueError) as error:
            return _malformed_result(f"Adapter output failed review validation: {error}")
        return {
            "status": "review-complete",
            "report": report,
            "evidence_unavailable": [],
            "message": None,
        }


def adapter_from_path(result_path: Path | None) -> ReviewAdapter:
    return FileReviewAdapter(result_path) if result_path is not None else NoReviewAdapter()


def _malformed_result(message: str) -> AdapterResult:
    return {
        "status": "malformed-output",
        "report": None,
        "evidence_unavailable": [message],
        "message": message,
    }


def _permission_result(message: str) -> AdapterResult:
    return {
        "status": "permission-denied",
        "report": None,
        "evidence_unavailable": [message],
        "message": message,
    }
