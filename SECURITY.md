# Security Policy

## Supported Versions

Quality Runner is pre-1.0. Security fixes are released on the latest tagged
minor version.

## Reporting a Vulnerability

Report security issues privately by opening a GitHub security advisory on the
repository. Do not disclose vulnerabilities publicly until a fix or mitigation
is available.

## Local-Only Boundary

Quality Runner is designed to run locally. It does not call remote services
during an audit. It reads repository files needed for quality evidence and
writes artifacts under `.quality-runner/runs/<run-id>/` in the target repository.

Generated artifacts can contain local repository evidence and should be handled
as potentially sensitive. Secret-like literals are redacted in security
candidates, code-quality findings, and remediation source excerpts before they
are persisted, but artifacts are not a guarantee of secret-free output. Report
any redaction bypass or behavior that reads or writes outside that boundary
through a private security advisory.
