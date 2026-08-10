## Supported behavior

- Added:
- Removed:

## Maintenance surface

Generate evidence when the branch has a meaningful production change:

```sh
qr maintenance-surface . --base origin/main --head HEAD \
  --behavior-added "..." \
  --consolidated-concept "..." \
  --handoff-output /tmp/maintenance-surface.md --json
```

- Production/test lines (descriptive, not a score):
- New dependencies:
- New public surfaces:
- New flags/configuration:
- Compatibility paths and removal conditions:
- Concepts consolidated or removed:
- Vertical-slice removal review:

## Verification

- Focused behavior checks:
- Full quality ladder:
- Regression proof (`verified`, `unavailable`, or not applicable):
- Forward-facing surface exercised:

## Limits and follow-up

- Unknown or blocked evidence:
- Owned follow-up / ADR / issue:
