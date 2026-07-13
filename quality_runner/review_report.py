"""Compatibility report builder retained until the M6 deprecation cutover."""

from quality_runner.application.review_reporting import (
    ADAPTER_STATUSES as _ADAPTER_STATUSES,
)
from quality_runner.application.review_reporting import (
    CLASSIFICATIONS as _CLASSIFICATIONS,
)
from quality_runner.application.review_reporting import (
    CONFIDENCES as _CONFIDENCES,
)
from quality_runner.application.review_reporting import (
    INCOMPLETE_REVIEW_SUMMARY as _INCOMPLETE_REVIEW_SUMMARY,
)
from quality_runner.application.review_reporting import (
    NO_ISSUE_CAVEAT as _NO_ISSUE_CAVEAT,
)
from quality_runner.application.review_reporting import (
    PACKET_READY_SUMMARY as _PACKET_READY_SUMMARY,
)
from quality_runner.application.review_reporting import (
    SEVERITIES as _SEVERITIES,
)
from quality_runner.application.review_reporting import (
    build_review_report as _build_review_report,
)
from quality_runner.core.review_contracts import ReviewFinding as ReviewFinding

ADAPTER_STATUSES = _ADAPTER_STATUSES
CLASSIFICATIONS = _CLASSIFICATIONS
CONFIDENCES = _CONFIDENCES
INCOMPLETE_REVIEW_SUMMARY = _INCOMPLETE_REVIEW_SUMMARY
NO_ISSUE_CAVEAT = _NO_ISSUE_CAVEAT
PACKET_READY_SUMMARY = _PACKET_READY_SUMMARY
SEVERITIES = _SEVERITIES
build_review_report = _build_review_report
