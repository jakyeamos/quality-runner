from __future__ import annotations

import json
from pathlib import Path

from quality_runner import schema_constants

SCHEMAS = {
    "workspace-snapshot.schema.json": schema_constants.WORKSPACE_SNAPSHOT_SCHEMA,
    "normalized-findings.schema.json": schema_constants.NORMALIZED_FINDINGS_SCHEMA,
    "prevention-readiness.schema.json": schema_constants.PREVENTION_READINESS_SCHEMA,
    "task-baseline.schema.json": schema_constants.TASK_BASELINE_SCHEMA,
    "task-check.schema.json": schema_constants.TASK_CHECK_SCHEMA,
    "task-record.schema.json": schema_constants.TASK_RECORD_SCHEMA,
    "dogfood-event.schema.json": schema_constants.DOGFOOD_EVENT_SCHEMA,
    "dogfood-report.schema.json": schema_constants.DOGFOOD_REPORT_SCHEMA,
    "dogfood-capture.schema.json": schema_constants.DOGFOOD_CAPTURE_SCHEMA,
}


def test_task_schemas_are_packaged_and_bound_to_public_schema_constants() -> None:
    schema_root = Path(schema_constants.__file__).parent / "schemas"

    for filename, schema_name in SCHEMAS.items():
        payload = json.loads((schema_root / filename).read_text(encoding="utf-8"))
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert payload["properties"]["schema"]["const"] == schema_name
        assert "schema" in payload["required"]


def test_task_check_schema_supports_all_cli_outcomes_and_canonical_evidence() -> None:
    schema_root = Path(schema_constants.__file__).parent / "schemas"
    payload = json.loads((schema_root / "task-check.schema.json").read_text(encoding="utf-8"))

    assert set(payload["properties"]["status"]["enum"]) == {
        "pass",
        "violation",
        "blocked",
        "invalid",
    }
    assert {
        "snapshot",
        "normalized_findings",
        "delta",
        "prevention_readiness",
        "gate_results",
        "blockers",
        "mode",
        "release_enforcement",
        "release_readiness",
        "next_action",
        "analysis",
        "evidence",
    } <= set(payload["properties"])


def test_task_record_schema_tracks_release_enforcement() -> None:
    schema_root = Path(schema_constants.__file__).parent / "schemas"
    payload = json.loads((schema_root / "task-record.schema.json").read_text(encoding="utf-8"))

    assert set(payload["properties"]["last_release_enforcement"]["enum"]) == {
        "advisory",
        "required",
    }


def test_task_payload_schemas_expose_telemetry_health_without_requiring_capture() -> None:
    schema_root = Path(schema_constants.__file__).parent / "schemas"

    for filename in ("task-baseline.schema.json", "task-check.schema.json"):
        payload = json.loads((schema_root / filename).read_text(encoding="utf-8"))
        assert payload["properties"]["dogfood_telemetry"] == {"$ref": "dogfood-capture.schema.json"}
