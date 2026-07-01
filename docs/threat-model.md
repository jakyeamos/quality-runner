# Threat Model

Quality Runner is a local-first audit tool. It inspects repository files and
writes evidence artifacts under `.quality-runner/runs/<run-id>/`. It does not
apply remediations, execute discovered commands, or call live CI/provider APIs.

## Boundaries

- Trusted code: the installed `quality-runner` package.
- Untrusted input: repository files, `.quality-runner.toml`, workflow files,
  local CI status JSON, package metadata, and generated artifact directories.
- Output boundary: `.quality-runner/runs/<run-id>/` plus explicit
  `export-handoff --output` paths.

## Controls

- Run ids must be a single path segment.
- Artifact directories and handoff reads reject symlinked path components.
- Symlinked CI paths and CI status files are skipped.
- Local CI status JSON must resolve inside the target repo.
- Large discovery/status files are ignored or warned on instead of read
  unbounded.
- Commands found in config, package scripts, Makefiles, Docker, Terraform, and
  workflows are recorded as evidence only; they are never executed.

## Residual Risks

- Conservative text scanning can miss unusual workflow YAML or Makefile syntax.
- Local CI status is only as trustworthy as the export supplied by the user.
- Surface detection is intentionally shallow; it identifies evidence for
  reviewer attention, not full semantic validity of infrastructure, contracts,
  or migrations.
