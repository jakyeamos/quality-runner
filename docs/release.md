# Release Checklist

Quality Runner publishes Python distributions from the `Release` GitHub
Actions workflow when a `v*.*.*` tag is pushed. For the current release cut,
the selected version is `0.7.0`; future releases must choose a new version
instead of reusing an existing tag or package release. For tag-triggered
publication, the workflow verifies that the tagged commit is an ancestor of
`main` before it can publish.

The package version has one source of truth in `quality_runner/_version.py` and
is read dynamically by package metadata. The release workflow installs the
built wheel before publishing and checks its CLI doctor contract, release smoke,
and MCP outcome-tool discovery alongside tag, plugin, and citation parity.

The selected version remains an unreleased candidate until the tag workflow has
completed and PyPI verification succeeds. Its committed `CITATION.cff`
metadata must match the tag; neither is evidence of publication by itself. The
checked-in Homebrew formula is an older `0.2.0` template, not current
published-release metadata; update it only after the selected source
distribution is live.

Release tags are permanent. Check the existing Git tags and PyPI releases before
choosing a new version; never reuse a tag, including `v0.5.0` or `v0.5.1`.

## Pre-tag validation

1. Confirm the committed toolchain and local ladder:

   ```bash
   uv sync --locked --all-groups
   uv run --locked pytest -q
   uv run --locked ruff check .
   uv run --locked ruff format --check .
   uv run --locked basedpyright
   uv run --locked vulture quality_runner quality_evidence_contract repo_quality_certifier tests scripts --min-confidence 70
   uv run --locked pip-audit
   uv run --locked quality-runner release-smoke --json
   uv build
   ```

2. Run a self-audit and review its capability findings, default structural
   findings, and high-severity security candidates:
   `uv run --locked quality-runner audit . --run-id pre-release-self-audit --json`.
   Candidate and agent-review items are heuristic obligations, not deterministic
   pass/fail verdicts; record the code-context review and do not tag with a
   confirmed vulnerability or unresolved structural defect.
3. Confirm the PyPI Trusted Publisher settings before tagging.
4. Review the [Upgrade and Compatibility Guide](upgrade.md), update
   `quality_runner/_version.py`, `quality_runner/plugin/manifest.json`, and
   `CITATION.cff` to the selected version, commit the release metadata, and
   merge the verified release branch to `main`.
5. Push the matching `v<version>` tag from that release commit.
6. Confirm the GitHub Actions release workflow publishes the package.
7. Verify the published artifact:

   ```bash
   uv tool install 'quality-runner==0.7.0' --force
   quality-runner --version
   quality-runner doctor --json
   quality-runner release-smoke --json
   printf '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n' | quality-runner-mcp
   ```

The normal refresh smoke records gate evidence but does not execute discovered
commands. If release proof requires executable gates, run it only with
`--execute-gates --worktree-mode disposable` and treat the result as arbitrary
local-code execution rather than a sandboxed check.

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
before pushing the selected version tag. The release must not be tagged until
these claims match the GitHub workflow.

## Homebrew

`packaging/homebrew/quality-runner.rb` is currently an older `0.2.0` template.
Use it only after the PyPI source distribution for the selected version is live.
Recompute the `sha256` from the published source artifact, update the formula
URL/version, run the formula install/audit checks, and commit the formula update
after PyPI verification.
