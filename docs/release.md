# Release Checklist

Quality Runner publishes Python distributions from the `Release` GitHub Actions
workflow when a `v*.*.*` tag is pushed.

## PyPI

1. Confirm the local ladder passes:
   - `python3.14 -m pytest -q`
   - `ruff check .`
   - `ruff format --check .`
   - `basedpyright`
   - `vulture . --min-confidence 70`
   - `uv build`
2. Configure PyPI Trusted Publishing for `jakyeamos/quality-runner`.
3. Push a version tag, for example `v0.1.0`.
4. Confirm the GitHub Actions release workflow publishes the package.
5. Verify:
   - `uv tool install quality-runner`
   - `quality-runner --version`
   - `quality-runner doctor --json`

### Trusted Publisher Settings

The release workflow uses GitHub OIDC and does not require a PyPI API token.
Because `quality-runner` does not exist on PyPI yet, create a pending publisher
from the PyPI account publishing page. Configure the pending GitHub publisher
with:

- PyPI project name: `quality-runner`
- Owner: `jakyeamos`
- Repository name: `quality-runner`
- Workflow filename: `release.yml`
- Environment name: `pypi`

The `v0.1.0` release run reached the publish step on 2026-06-28 and failed with
`invalid-publisher`, which means PyPI did not have a matching trusted publisher
for those claims yet. After adding the pending publisher, rerun the release
workflow or repush the version tag.

## Homebrew

Use `packaging/homebrew/quality-runner.rb` as the initial formula template after
the PyPI source distribution is live. Recompute the `sha256` from the published
source artifact before opening a tap PR.
