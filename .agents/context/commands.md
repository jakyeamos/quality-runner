# Commands and quality gates

last_reviewed: 2026-07-22

Use the locked development environment and run gates from the repository root.

```text
uv sync --locked --all-groups --python 3.14
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked basedpyright
uv run --locked vulture quality_runner quality_evidence_contract repo_quality_certifier tests scripts --min-confidence 70
uv run --locked pip-audit
uv build
python scripts/check_environment_contract.py
```

For a focused change, run the narrowest relevant test first and then the full
suite. `qr doctor --json` is a read-only readiness check. The exact CLI
journeys are documented in [docs/cli.md](../../docs/cli.md), and recovery
guidance is in [docs/troubleshooting.md](../../docs/troubleshooting.md).

The Pre-CR adapter is required; do not remove it to make a gate green.
