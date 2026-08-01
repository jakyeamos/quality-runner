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
        "next_action",
        "analysis",
        "evidence",
    } <= set(payload["properties"])
