# Verification signals

Quality Runner's repository scan reports two useful declarations inspired by
the coverage and mutation portions of the anti-slop checklist:

- `coverage` identifies an explicit coverage flag, coverage tool, or
  coverage-named command.
- `mutation` identifies an explicit mutation runner, mutation flag, or
  mutation-named command.

These are declarations, not results. Each signal includes the source and a
small explanation of what matched. `execution: not_observed` is intentional:
repository discovery is read-only and does not run a target repository's
commands or trust an unbound report. A repository with no inspectable command
surface is `unknown`; one with commands but no recognized declaration is
`not_declared`.

For an actual quality claim, a later verification run must bind the result to
the target revision, producer/tool version, configuration, and report
artifact. A configured coverage command does not prove a percentage, and a
configured mutation command does not prove that survivors are zero. This keeps
the useful part of the checklist while avoiding a universal threshold or a
false pass from stale or unavailable evidence.
