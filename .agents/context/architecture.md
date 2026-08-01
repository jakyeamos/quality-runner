# Architecture and boundaries

Quality Runner inspects a target repository, compiles standards, discovers
available quality gates, normalizes evidence-backed findings, and writes a
remediation plan. It is an orchestrator for evidence, not an implementation
agent.

The main boundaries are:

- `quality_runner/discovery.py` and `quality_runner/scan_scope.py` discover
  repository facts and bounded scan inputs;
- `quality_runner/standards.py`, `quality_runner/capabilities.py`, and the
  code-quality modules compile standards and available gates;
- `quality_runner/audit.py`, `quality_runner/findings.py`, and
  `quality_runner/remediation_*.py` normalize findings and bounded slices;
- `quality_runner/gate_execution.py`, `quality_runner/verification_contract.py`,
  and `quality_runner/worktree_verify.py` enforce evidence-only or explicitly
  disposable execution modes;
- `quality_runner/cli*.py` and `quality_runner/mcp.py` expose human and MCP
  interfaces; `repo_quality_certifier/` preserves the compatibility surface;
- `.quality-runner/runs/<run-id>/` is the target artifact boundary. Source
  repositories are inputs, not write destinations for remediation.

The data flow is:

`bounded repository inputs -> standards/capabilities -> audit findings ->
remediation slices and handoff -> optional verified evidence`

The package must not call model providers, collect credentials, publish
artifacts, create commits, or silently execute discovered commands. Any
future integration must preserve explicit consent, disposable worktrees, and
provenance in the output contract.
