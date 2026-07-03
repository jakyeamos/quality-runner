# Release Checklist

Quality Runner publishes Python distributions from the `Release` GitHub Actions
workflow when a `v*.*.*` tag is pushed. The next release tag is `v0.2.1`.

Do not reuse `v0.1.0` or `v0.2.0`. `v0.1.0` already reached the PyPI publish
step on 2026-06-28 and failed because the PyPI Trusted Publisher was not
configured for the GitHub OIDC claims. `v0.2.0` was published on 2026-07-02.

## PyPI

1. Confirm the local ladder passes:
   - `quality-runner release-smoke --json`
   - `python3.14 -m pytest -q`
   - `ruff check .`
   - `ruff format --check .`
   - `basedpyright`
   - `vulture . --min-confidence 70`
   - `uv run --with pytest pytest -q`
   - `python3.14 scripts/run_pytest_with_lcov.py`
   - `uv build`
   - `pre-cr run --workspace . --json`
2. Run a self-audit and confirm there are no capability blockers and no default
   structural findings:
   - `quality-runner run . --run-id pre-release-self-audit --json`
3. Confirm the PyPI Trusted Publisher settings before tagging.
4. Merge the verified release branch to `main`.
5. Push `v0.2.1`.
6. Confirm the GitHub Actions release workflow publishes the package.
7. Verify the published artifact:
   - `curl -sS https://pypi.org/pypi/quality-runner/0.2.1/json`
   - `uv tool install quality-runner==0.2.1 --force`
   - `quality-runner --version`
   - `quality-runner doctor --json`
   - `quality-runner release-smoke --json`
   - `quality-runner refresh /path/to/small/repo --run-id-prefix release-smoke --handoff-output /tmp/release-smoke-handoff.md --json`

## Handoff Examples

Use these examples when checking whether generated handoffs are readable without
opening raw JSON artifacts:

- [Clean handoff](examples/handoff-clean.md)
- [Blocked handoff](examples/handoff-blocked.md)
- [Timeout handoff](examples/handoff-timeout.md)

### Trusted Publisher Settings

The release workflow uses GitHub OIDC and does not require a PyPI API token.
Before tagging, confirm PyPI has a pending or active trusted publisher with:

- PyPI project name: `quality-runner`
- Owner: `jakyeamos`
- Repository name: `quality-runner`
- Workflow filename: `release.yml`
- Environment name: `pypi`

If that publisher is missing, create it from the PyPI account publishing page
before pushing `v0.2.1`. The release must not be tagged until these claims match
the GitHub workflow.

## Homebrew

Use `packaging/homebrew/quality-runner.rb` as the formula template after the
PyPI source distribution for `0.2.1` is live. Recompute the `sha256` from the
published source artifact, update the formula URL/version, run the formula
install/audit checks, and commit the formula update after PyPI verification.
