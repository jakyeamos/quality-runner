# Failure modes and recovery

last_reviewed: 2026-08-11

- Worktree creation failure blocks dynamic verification; verify target Git
  provenance and execution authority before retrying.
- Dependency setup timeout is not a check failure. Record setup separately and
  prevent package managers from silently reinstalling copied dependency trees.
- A dynamic repository that exceeds its coordinator watchdog becomes a
  first-class timeout finding and must not stall later repositories. QR-owned
  subprocesses use dedicated process groups; cleanup retains the original
  group id and escalates after the leader exits so inherited pipes cannot keep
  the coordinator blocked.
- Replay or feed validation failure blocks publication. Repair the snapshot and
  rerun replay before replacing the current feed.
- Stale or unknown evidence remains explicit and cannot be upgraded from a
  prior score or source-only result.
