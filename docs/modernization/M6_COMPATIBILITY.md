# M6 Compatibility Boundaries

M6 makes the application layer the single owner of audit, verification, and
journey-outcome execution while preserving installed module paths and v1 output
contracts.

| Legacy surface | Implementation owner | Compatibility guarantee |
| --- | --- | --- |
| `quality_runner.workflow.inspect_payload` / `run_payload` | `application.audit_workflows` | Existing function names, arguments, schemas, status values, artifact paths, and warning order remain unchanged. |
| `quality_runner.workflow.verify_gates_payload` and `workflow_verify` | `application.verification_workflows` | Existing gate payload schema, authorization behavior, and artifacts remain unchanged. |
| `quality_runner.workflow.refresh_payload` | `compatibility.legacy_workflow` | The root façade retains injectable inspect/run/verify/summary collaborators for legacy test and controller behavior. Review-delta attachment remains in the compatibility adapter. |
| `compatibility.journey_outcomes` | `application.journey_outcomes` and `compatibility.review_mcp` | Legacy imports preserve v2 outcome schemas, branch-switch evidence, and MCP tool names. Raw MCP review arguments remain in an adapter rather than the application layer. |

Internal CLI and MCP consumers now call application-owned audit, verification,
and journey services directly. Root workflow modules remain public façades only.
Application-owned workflow modules must not import root workflow, compatibility,
or CLI adapter modules; `tests/test_compatibility_boundaries.py` enforces that
direction.

The repository certifier, scanner contracts, and review-packet compatibility
surfaces are intentionally outside this extraction. They retain their existing
public paths until their own migration contract is complete.
