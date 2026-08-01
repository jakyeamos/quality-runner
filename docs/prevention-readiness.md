# Prevention readiness

Quality Runner treats a repository command as preventative only after it has a
resolved executable and version, a documented bootstrap, repeatable passing
behavior, an intentional failure fixture, local evidence, and CI evidence.
Merely appearing in CI is not certification.
Repositories may explicitly mark a proposed gate `blocked` or `unavailable`
with a concrete blocker; readiness preserves that state instead of presenting
the gate as a usable candidate.

Prevention uses a hybrid feedback model:

- Agent guidance requires a task baseline and an authoritative completion
  check, and explains how to respond to each result.
- Mature repository-native checks provide faster feedback during editing.
- QR independently verifies the exact workspace, task-relative finding delta,
  comparable coverage, policy hashes, and certified gate evidence.

Static agent rules are not evidence that a check ran and cannot distinguish
legacy debt from a new occurrence, incomplete coverage from resolution, or a
violation from an evidence blocker. Conversely, QR is not intended to run on
every save. The supported cadence is baseline, implementation-time native
feedback where mature, QR completion check, and PR CI; full scans remain an
audit/nightly boundary.

The first Quality Runner certification covers the locked development environment
created by `uv sync --locked --all-groups --python 3.13`:

| Gate | Pinned version | Local command | CI command |
| --- | --- | --- | --- |
| pytest | 9.0.3 | `pytest -q` | `uv run --locked pytest -q` |
| Ruff lint | 0.15.10 | `ruff check .` | `uv run --locked ruff check .` |
| Ruff format | 0.15.10 | `ruff format --check .` | `uv run --locked ruff format --check .` |
| BasedPyright | 1.39.0 | `basedpyright` | `uv run --locked basedpyright` |

`tests/test_prevention_policy.py` supplies repeat-pass and intentional-failure
fixtures for each gate. `.github/workflows/ci.yml` runs the equivalent pinned
commands on Python 3.12, 3.13, and 3.14 on Ubuntu and macOS. `qr task` resolves
the executable from `.venv/bin`, records the path and `--version` output, and
runs only certified commands inside its isolated source snapshot. Before those
commands run, QR executes each distinct certified bootstrap once in the
snapshot, records the bootstrap executable, version, output, and status, then
prefers the tools installed into the snapshot's `.venv`. A failed, missing,
unversioned, or timed-out bootstrap blocks the check instead of being treated as
a policy violation. Gate subprocesses do not inherit user or system Git
configuration, caller-selected Python import paths, UV Python, or virtual
environments, so global ignore rules, hooks, and launcher state cannot make
local evidence differ from CI. The documented `uv` cache may be reused, but the
locked environment is materialized independently for each task-check snapshot.

The first promoted QR rule is `code_quality:large-source-file`. Its positive,
negative, and test-scope/ambiguous boundary fixtures are also in
`tests/test_prevention_policy.py`. No other QR rule is enforced by this policy.

To refresh local evidence, run:

```bash
uv sync --locked --all-groups --python 3.13
uv run --locked pytest -q tests/test_prevention_policy.py
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked basedpyright
```

Any tool, configuration, policy, or rule-pack hash change requires
`qr task rebaseline --reason ...`; the prior baseline remains in the task
lineage.

The pull-request workflow is intentionally a non-authoritative pilot during
self-dogfooding. Remove `continue-on-error` only after both local and CI task
checks pass with equivalent pinned tools and complete evidence.
