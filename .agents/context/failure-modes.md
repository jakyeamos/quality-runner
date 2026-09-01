# Common failure modes and recovery

Last reviewed: 2026-09-01

- **Locked environment unavailable:** restore the documented `uv sync --locked
  --all-groups` environment. Do not replace locked commands with an unpinned
  install or claim a partial run is equivalent.
- **Pre-CR reports `no-changes`:** this is expected on an unchanged checkout;
  use the full ladder for baseline evidence and run Pre-CR only after a real
  changed-line slice exists.
- **Dirty target or unsafe gate execution:** preserve the checkout. Run the
  Quality Runner gate in an explicitly disposable worktree when the target
  cannot be safely inspected in place. This is a gate-execution prerequisite,
  not a general implementation-lane rule; a dirty `dev` alone does not select
  a feature branch. Never clean or reset a user tree to make a gate run.
- **Gate timeout or unavailable tool:** retain the timeout/availability result,
  identify the missing prerequisite, and rerun only after the environment is
  repaired. Do not turn a timeout into a pass.
- **Artifact validation or redaction failure:** keep the raw result private,
  repair the smallest owning transform, and add a regression fixture before
  retrying.
- **Schema or compatibility snapshot changes:** inspect the contract diff,
  update versioned snapshots deliberately, and run the compatibility suite.
- **Release smoke failure:** keep the built artifact and diagnostics, fix the
  smallest owned surface, and repeat the full release ladder before publishing.
