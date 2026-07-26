# Common failure modes and recovery

- **Locked environment unavailable:** restore the documented `uv sync --locked
  --all-groups` environment. Do not replace locked commands with an unpinned
  install or claim a partial run is equivalent.
- **Pre-CR reports `no-changes`:** this is expected on an unchanged checkout;
  use the full ladder for baseline evidence and run Pre-CR only after a real
  changed-line slice exists.
- **Dirty target or unsafe worktree:** preserve the checkout and use an
  explicitly disposable worktree. Never clean or reset a user tree to make a
  gate run.
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
