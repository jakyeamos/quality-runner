# Prevention readiness

Quality Runner treats a repository command as preventative only after it has a
resolved executable and version, a documented bootstrap, repeatable passing
behavior, an intentional failure fixture, local evidence, and CI evidence.
Merely appearing in CI is not certification.

The first Quality Runner certification covers the locked development environment
created by `uv sync --locked --all-groups`:

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
runs only certified commands inside its isolated source snapshot. Gate
subprocesses do not inherit user or system Git configuration, so global ignore
rules and hooks cannot make local evidence differ from CI. The documented
bootstrap environment supplies the pinned dependency cache; QR does not install
or update dependencies during a task check.

The first promoted QR rule is `code_quality:large-source-file`. Its positive,
negative, and test-scope/ambiguous boundary fixtures are also in
`tests/test_prevention_policy.py`. No other QR rule is enforced by this policy.

To refresh local evidence, run:

```bash
uv sync --locked --all-groups
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
