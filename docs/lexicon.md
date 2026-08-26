# Quality Runner Lexicon

This page defines canonical shorthand used by people and agents. A term here
expands to the complete workflow below; it does not weaken Quality Runner's
evidence, custody, or safety contracts.

## Full QR

**Full QR** is the canonical shorthand for a full canonical Quality Runner
assessment of one repository at an exact committed target. It is a workflow
phrase, not a single CLI subcommand.

The request `Run a Full QR on /path/to/repository` requires all four jobs:

1. **Inspect code.** Run complete source analysis with every applicable
   standard, profile, skill pack, and detector, and complete the qualitative
   agent review for every applicable judgment-based rubric.
2. **Execute and record gates.** Run every applicable repository-defined gate
   in the documented disposable exact-target environment, including formatting,
   lint, type checking, tests, builds, dead-code checks, dependency and security
   checks, runtime smoke, UI and accessibility checks, web readiness, and
   release checks. Classify every unavailable, blocked, or not-applicable gate;
   never omit it silently.
3. **Assess readiness.** Evaluate the applicable onboarding, repository hygiene,
   CI, security, web, and release-readiness contracts from the same exact target
   and evidence set.
4. **Preserve evidence.** Bind immutable receipts to the exact repository,
   branch, and commit; import the canonical receipt into Pronto; and read back
   the projection so capture is not mistaken for successful consumption.

Using **Full QR** is explicit authorization to execute applicable repository
gates only through Quality Runner's documented disposable-worktree path. It does
not authorize dependency installation, target-source edits, remediation,
commits, pushes, publication, deployment, credentials, or remote service calls.
Those actions require separate authorization.

A Full QR may truthfully finish `blocked`, `incomplete`, or `not_applicable` for
part of its scope. It may not silently reduce scope and report completion. A
detector-only run, `--analysis-mode full`, a "full scan," or a "complete scan"
changes source-analysis breadth only and is not a Full QR.
