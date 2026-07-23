# Definition of done

last_reviewed: 2026-07-22

A change is complete when:

- the affected contract and ownership boundary are documented;
- focused regression tests cover changed behavior and safety boundaries;
- `pytest`, Ruff lint/format, BasedPyright, Vulture, and relevant security or
  build gates pass, or their exact failures are recorded;
- generated artifacts are either reproducible and ignored or intentionally
  versioned with provenance;
- no target checkout, remote, provider, deployment, or publication changed
  without explicit authorization;
- `.tracker/PROJECT_TRUTH.md` records the current state and next step.

Use [CONTRIBUTING.md](../../CONTRIBUTING.md), the
[release profile](../../docs/release.md), and the current
[project truth](../../.tracker/PROJECT_TRUTH.md) for scope-specific acceptance.
