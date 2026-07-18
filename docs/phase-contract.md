# GSD phase contracts

Quality Runner can evaluate a bounded GSD phase without treating the repository-wide finding total as the phase status.

Create a contract with the `quality-runner-phase-contract-v0.1` schema:

```json
{
  "schema": "quality-runner-phase-contract-v0.1",
  "phase_id": "67",
  "plan_id": "67-01",
  "baseline_run_id": "qr-phase-67-baseline-verify",
  "scan_tier": "phase",
  "scope": {"include_paths": ["src/security"]},
  "finding_map": [
    {"fingerprints": ["<fingerprint>"], "plan_id": "67-01", "task_id": "T1"}
  ],
  "dispositions": [],
  "early_refresh_triggers": ["unexpected fingerprint drift"]
}
```

Use `--phase-contract` with `refresh` to derive the scoped scan paths. Use `phase-check` after the phase refresh to write `phase-closure.json` and `phase-closure.md` into the current run directory.

QR reports new, persisted, resolved, out-of-scope, actionable, dispositioned, and unmapped findings. Closure is blocked by actionable or unmapped findings, invalid accepted dispositions, or a recommended early refresh. QR writes evidence artifacts only; GSD remains the owner of `.planning/ROADMAP.md`, `.planning/STATE.md`, plan files, execution, and commits.
