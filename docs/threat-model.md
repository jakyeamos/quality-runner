# Threat Model

Quality Runner is a local-first audit tool. It inspects repository files and
writes evidence artifacts under `.quality-runner/runs/<run-id>/`. It does not
apply remediations or call live CI/provider APIs. Discovered commands are
evidence-only unless a caller explicitly authorizes disposable execution.

## Boundaries

- Trusted code: the installed `quality-runner` package.
- Untrusted input: repository files, `.quality-runner.toml`, workflow files,
  local CI status JSON, package metadata, existing artifact trees, and
  compatibility-certifier output paths.
- Output boundary: `.quality-runner/runs/<run-id>/` plus explicit handoff,
  controller-report, and rollout output paths.

## Controls

- Run ids must be a single path segment.
- Artifact readers and writers reject symlinked namespace components and leaves.
- Explicit output paths reject symlinked ancestors and leaves.
- Compatibility-certifier run ids, rubric ids, and output directories are
  containment-checked; it does not edit `.git/info/exclude`.
- Symlinked CI paths and CI status files are skipped.
- Local CI status JSON must resolve inside the target repo.
- Artifact-derived Git revisions must be full object identifiers and are passed
  to Git as option-delimited revision arguments.
- Large discovery/status files are ignored or warned on instead of read
  unbounded.
- Secret-like security candidates, code-quality findings, and remediation
  source excerpts redact quoted literals before fingerprinting and artifact
  persistence; derived audit and handoff evidence uses the redacted excerpt.
- Commands found in config, package scripts, Makefiles, Docker, Terraform, and
  workflows are recorded as evidence only by default. Execution requires both
  `--execute-gates` and `--worktree-mode disposable`.

## Residual Risks

- Conservative text scanning can miss unusual workflow YAML or Makefile syntax.
- Local CI status is only as trustworthy as the export supplied by the user.
- Surface detection is intentionally shallow; it identifies evidence for
  reviewer attention, not full semantic validity of infrastructure, contracts,
  or migrations.
- Redacted candidate evidence does not make generated artifacts secret-free.
  Repository paths, author intent, other source-derived context, and bounded
  stdout/stderr from authorized gates can still be sensitive. Handle artifacts
  according to the [Artifact Contract](artifacts.md#handling-generated-artifacts).
- An explicitly authorized command is arbitrary local code. A disposable
  checkout protects the ordinary source worktree from normal mutations, not the
  host, network, secrets, or deliberate path escape; dirty-worktree opt-in
  verifies `HEAD` rather than local edits.
