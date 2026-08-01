# Canonical commands and quality gates

Run from the repository root with the locked development environment:

```sh
uv sync --locked --all-groups
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked basedpyright
uv run --locked vulture quality_runner quality_evidence_contract repo_quality_certifier tests scripts --min-confidence 70
uv run --locked pip-audit
uv build
python3 scripts/check_environment_contract.py
```

For the complete pre-release path, also run:

```sh
uv run --locked python scripts/run_pytest_with_lcov.py
uv run --locked qr release-smoke --json
```

`pre-cr run --workspace . --json` is a changed-line readiness check. It is
expected to report `no-changes` on an unchanged checkout; it is not a
replacement for the full ladder above. CI and release workflows are the
authoritative remote declarations of the same gates.

`.quality-runner.toml` declares the security dependency audit and environment
contract as required blocker gates. The local checker and both remote workflows
must remain in agreement with that declaration.

The repository commit hook uses `hookTimeoutSeconds: 360` in `.pre-cr.json`.
This budget covers the traced changed-line runner on this repository; lower it
only after a measured replacement run establishes a smaller safe bound.

Quality commands must be bounded and offline-capable. They must not publish,
deploy, tag, push, call a provider, collect credentials, or execute a
remediation action. If a dependency cache, tool, or gate is unavailable, keep
the result visible as unknown or blocked.

BasedPyright is certified over the declared package scope in standard mode.
Repository-wide strict mode is not certified: the 0.7.0 fold exposed a large
existing backlog when the environment branch enabled it without end-to-end
proof. Keep that migration visible as candidate work, fix findings at their
source, and do not add broad ignores or replace errors with casts.
