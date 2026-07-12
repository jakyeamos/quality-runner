from __future__ import annotations

import json
from importlib import resources


def test_gate_verification_schema_allows_synthetic_workflow_timeout_gates() -> None:
    schema_path = resources.files("quality_runner").joinpath(
        "schemas/gate-verification.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    gate_properties = schema["$defs"]["gate"]["properties"]

    assert "workflow-timeout" in gate_properties["failure_type"]["enum"]
    assert gate_properties["phase"] == {"type": "string", "minLength": 1}
    assert gate_properties["timeout_diagnostics"] == {"type": "object"}
