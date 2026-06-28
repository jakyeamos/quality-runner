# Security Policy

## Supported Versions

Quality Runner is pre-1.0. Security fixes are released on the latest tagged
minor version.

## Reporting a Vulnerability

Report security issues privately by opening a GitHub security advisory on the
repository. Do not disclose vulnerabilities publicly until a fix or mitigation
is available.

## Local-Only Boundary

Quality Runner v1 is designed to run locally. It does not call remote services
during an audit. It reads repository files needed for quality evidence and writes
artifacts under `.quality-runner/runs/<run-id>/` in the target repository.

Report any behavior that reads or writes outside that boundary.
