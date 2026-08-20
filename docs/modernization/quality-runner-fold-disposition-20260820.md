# Quality Runner fold disposition — 2026-08-20

This ledger records the source-lane fold performed on
`codex/fold-c-quality-runner-verification`. It is the authority for deleting
the candidate refs below; the target count alone is not deletion evidence.

## Boundary and counts

- Before this fold: 26 candidate local `codex/*` refs, plus the retained fold
  ref; 3 candidate `origin/codex/*` refs were still advertised remotely.
- Retained checkout: one clean task worktree on
  `codex/fold-c-quality-runner-verification`.
- Fold commits added in this pass: `5cb7152` (remove obsolete project-truth
  artifact) and `9a17ab7` (document subprocess fixture contract).
- Current verification baseline after the earlier QR repairs:
  `b2c089e` passed the full suite (1,225 tests), focused repair tests, Ruff,
  and the repository pre-CR hook.
- Intended cleanup result: 0 candidate local refs and 0 candidate remote refs;
  the fold ref, `dev`, `main`, and their normal remote-tracking refs remain.

## Dispositions

Each `superseded` row names the newer implementation or direct behavior proof
that replaces the candidate. `absorbed` means the candidate's useful change is
present in the fold branch. No row is retained as unknown or legacy-only.

| Candidate ref | Tip | Disposition and proof |
| --- | --- | --- |
| `codex/behavior-assurance-cli` | `41f8629` | **Superseded.** Current behavior-assurance primitives are in `d033674` and later fleet behavior modules; current receipt code is newer than the candidate and the full QR suite passes. |
| `codex/ci-prompt-bridge-quality-runner-final` | `1d34c54` | **Superseded.** Current workflow is present and newer through `84cc44c`, `1a28af6`, `7f79f0b`, and `ec8936e`; the checked workflow is the rerun-aware version. |
| `codex/ci-prompt-bridge-quality-runner-main-v2` | `cb3be6a` | **Superseded.** Same Codex CI prompt consumer is present at the current tip with the final artifact pin and rerun handling. |
| `codex/ci-prompt-bridge-rerun-aware` | `f19d702` | **Absorbed.** `.github/workflows/codex-ci-prompt.yml` is byte-identical to the candidate's final workflow. |
| `codex/ci-warning-cleanup` | `633bb21` | **Absorbed.** No unique non-merge patch remains against the current fold; current CI and pre-CR gates pass. |
| `codex/compass-drafts-quality-runner-0814` | `8ab1657` | **Absorbed.** No unique non-merge patch remains; current compass draft surfaces are in the fold history. |
| `codex/compass-fleet-registry-53` | `0136a80` | **Absorbed.** No unique non-merge patch remains; current fleet registry and audit surfaces are present. |
| `codex/compass-quiz-quality-runner-0814` | `bb93601` | **Absorbed.** No unique non-merge patch remains; current quiz/compass surfaces are in the fold history. |
| `codex/failure-visibility-capability` | `286ace4` | **Superseded.** Current implementation is `ff37bef` plus later compatibility repairs; failure-visibility tests and the full suite pass. |
| `codex/fleet-certification-aggregator` | `3f056da` | **Absorbed.** Certification implementation, schema, CLI, coordinator integration, and tests are present at `2ffff6a` and current `fleet certify` help is live. |
| `codex/fleet-detector-diagnostics-and-ids` | `754913e` | **Superseded.** Deadline, evidence, callback, and detector behavior are represented by current `f6ad082`, `7880246`, `f8fe423`, and `597e974`; detector tests pass. |
| `codex/fleet-detector-refresh-operational` | `c92450a` | **Superseded.** The detector-refresh implementation and restored gates are newer in the current fold; current detector tests and the full suite pass. |
| `codex/fleet-detector-refresh-tmp` | `7d93d0b` | **Superseded.** The older refresh implementation is replaced by current `597e974` and its deadline/evidence follow-ups. |
| `codex/fleet-refresh-scope-metadata` | `7963b92` | **Absorbed.** Callback contract behavior is in `f8fe423`; shared scan-scope behavior is in `e159aef`, with focused parity tests green. |
| `codex/main-fold-fleet-detector-refresh` | `c3c467f` | **Superseded.** The older main-fold detector tree is replaced by the current detector implementation and workflow-boundary tests. |
| `codex/maturity-evidence-scoring-20260801` | `431eda8` | **Superseded.** Evidence scoring is in current `1912ea7`; dimension evidence tests pass and current legibility is further split/refined. |
| `codex/preserve/quality-runner-067b-lcov-parity` | `4c4f82c` | **Superseded.** Current staged `--changed-only` LCOV selection/import behavior replaces the older selector; `tests/test_lcov_script.py` and the full suite pass. |
| `codex/preserve/quality-runner-067b-quality-runner-9319200` | `9319200` | **Absorbed.** Scan-scope parity is current `e159aef`; obsolete project-truth cleanup was folded as `5cb7152`. |
| `codex/preserve/quality-runner-127f-resolution-similarity` | `bf13bfc` | **Superseded.** Resolution provenance is current `bb6434c`; current timeout, lexer, redaction, audit-artifact, and LCOV code contain newer compatible hardening, verified by the full suite. |
| `codex/preserve/quality-runner-flexible-scan-dirty-20260815` | `2847074` | **Superseded.** All 77 paths changed by the snapshot exist in the current fold; 34 are byte-identical and 43 have newer current content. Current maturity, behavior, detector, feed, and custody tests pass. |
| `codex/qr-command-surface` | `14f3031` | **Superseded.** Current `qr` is the canonical CLI and `quality-runner` remains its compatibility alias. The candidate would delete 803 current files and is not a safe source of upgrades. |
| `codex/qr-maturity-feed-external-scope-20260803` | `fbc55cd` | **Superseded.** Authorized external feed-root behavior is current `2d2ca8d` plus newer coordinated feed/checkpoint logic and tests. |
| `codex/qr-maturity-feed-july29-integration-20260803` | `2b5292d` | **Superseded.** Its invariant/release typing cleanup is present in later current commits; its fixture documentation slice was absorbed as `9a17ab7`. |
| `codex/qr-visibility-hotspots-qr-20260814` | `899def9` | **Superseded.** Change-surface hotspots are current and byte-identical; documentation visibility is newer in `d8f462a` with current visibility tests. |
| `codex/quality-runner-custom-ci-gate-audit-20260811` | `9c1f24c` | **Absorbed.** CI-gate audit source, schema, CLI, fleet projection, and tests are present in current `989a17b`; the full suite passes. |
| `codex/quality-runner-semantic-v4` | `7825228` | **Superseded.** Mac Control source-grounding v2 is present in current `9a2d8e2` and later provenance/test refinements; the older v4 branch would regress source and sidecar validation. |

## Fold conflicts and repairs

- The attempted Mac Control cherry-pick was aborted before changing the tree:
  the candidate would have removed current v2 source/provenance checks.
- The project-truth fold produced one explicit modify/delete conflict because
  the current checkout had a stale copy. The deletion was resolved explicitly,
  producing `5cb7152`; no user source was discarded.
- Earlier scan-scope and provenance cherry-picks were resolved in the current
  architecture and are covered by `e159aef`, `bb6434c`, and `b2c089e`.

## Retained paths

- `codex/fold-c-quality-runner-verification` remains the one clean task-owned
  source lane until it is fast-forwarded to `dev`.
- `dev` and `main` remain protected canonical branches; no `main` mutation is
  authorized by this ledger.
- No candidate worktree is attached to the 26 refs above. The separate QR audit
  worktree under `~/.quality-runner/fleet-audit/` is retained until its audit
  ownership and recoverability are rechecked during final cleanup.
