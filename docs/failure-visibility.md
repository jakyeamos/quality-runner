# Failure visibility capability

`failure_visibility` is an opt-in executable capability for repositories whose
important fallback, degradation, or evidence paths can otherwise make failed
work look successful or absent. It is deliberately broader than a single
incident and narrower than generic test coverage.

## Contract

A qualifying repository gate must exercise representative negative paths and
assert their machine-readable readback. At minimum:

- an unavailable dependency or evidence source remains `unavailable`,
  `blocked`, or another explicit non-success state;
- a fallback exposes that it activated, its source, its reason, and the
  observation or freshness boundary when those fields apply;
- malformed, stale, partial, and contradictory input cannot be normalized into
  verified success;
- the gate exits non-zero when any of those postconditions fail.

The gate does not replace unit tests, runtime smoke tests, telemetry, or an
external probe. It connects them at the consumer boundary where a silent
failure would become misleading output.

```toml
[quality_runner]
required_capabilities = ["lint", "tests", "failure_visibility"]

[[quality_runner.gates]]
id = "failure_visibility"
command = "pnpm failure-visibility"
ecosystem = "javascript"
source = "repository negative-path contract"
owner = "platform"
required = true
severity = "blocker"
mutating_risk = "safe"
```

Quality Runner recognizes `failure-visibility`, `failure_visibility`,
`failure-paths`, and `test:failure-visibility` package scripts. The capability
is not added to the built-in default or release requirement sets; fleet rollout
can therefore begin report-only, and repositories opt in when the contract is
applicable and executable.

## Evidence states

Capability entries expose `evidence_state` without weakening the existing
`verification_state` compatibility object:

- `configured`: a runnable contract was discovered but not executed;
- `covered`: CI evidence exists but is pending, stale, or not bound to the
  current branch and commit;
- `fresh_passing`: local execution passed, or CI success is current,
  commit-bound, branch-bound, and captured within 24 hours;
- `failed` or `blocked`: a current execution produced that outcome;
- `unavailable`: a required capability has no valid command;
- `not_applicable`: a bounded exception is active.

Successful CI without current provenance is only `covered`, never
`fresh_passing`. Accepted exceptions require a non-empty owner and reason plus
an ISO expiry date; invalid or expired exceptions do not suppress a missing
capability.

## Static companion checks

Quality Runner's high-confidence `harden` rules flag empty JavaScript catches
and Python `except` handlers whose only body is `pass`. These findings identify
likely swallowed failures but are not a substitute for the executable
capability: static scanning cannot prove that fallbacks, UI state, telemetry,
or downstream readback remain truthful.
