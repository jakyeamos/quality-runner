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

Quality commands must be bounded and offline-capable. They must not publish,
deploy, tag, push, call a provider, collect credentials, or execute a
remediation action. If a dependency cache, tool, or gate is unavailable, keep
the result visible as unknown or blocked.
