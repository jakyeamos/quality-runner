# Canonical implementation examples

- `quality_runner/verification_contract.py` and
  `quality_runner/gate_provenance.py` show how gate results retain explicit
  evidence and execution-mode metadata.
- `quality_runner/source_evidence_redaction.py` and
  `quality_runner/evidence_redaction_contract.py` show the boundary between
  evidence collection and persisted redacted output.
- `quality_runner/core/*_contracts.py` and `quality_runner/schemas/` are the
  references for versioned artifact shapes.
- `tests/test_cli.py`, `tests/test_workflow.py`, and the gate-preflight tests
  are the canonical examples for public behavior and safety contracts.
- `scripts/run_pytest_with_lcov.py` is the reference for a bounded, local
  quality helper that writes only its declared `.pre-cr/` output.

Examples and fixtures must remain synthetic or public-safe. New examples should
show the smallest valid contract and must not embed local paths, credentials,
raw prompts, or unpublished repository evidence.
