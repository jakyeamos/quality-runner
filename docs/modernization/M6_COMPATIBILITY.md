# M6 Compatibility Boundaries

M6 makes the application layer the single owner of audit, verification, and
journey-outcome execution while preserving installed module paths and v1 output
contracts.

| Legacy surface | Implementation owner | Compatibility guarantee |
| --- | --- | --- |
| `quality_runner.workflow.inspect_payload` / `run_payload` | `application.audit_workflows` | Existing function names, arguments, schemas, status values, artifact paths, and warning order remain unchanged. |
| `quality_runner.workflow.verify_gates_payload` and `workflow_verify` | `application.verification_workflows` | Existing v0.1 artifacts remain readable. Consent-aware verification emits the versioned v0.2 gate schema; clients must branch on its `schema` value rather than parse it as v0.1. |
| `quality_runner.workflow.refresh_payload` | `compatibility.legacy_workflow` | The root façade retains injectable inspect/run/verify/summary collaborators for legacy test and controller behavior. Review-delta attachment remains in the compatibility adapter. |
| `compatibility.journey_outcomes` | `application.journey_outcomes` and `compatibility.review_mcp` | Legacy imports preserve v2 outcome schemas, branch-switch evidence, and MCP tool names. Raw MCP review arguments remain in an adapter rather than the application layer. |
| `quality_runner.review_context` | `application.review_context_factory` | Root wrappers retain v1 type annotations and injectable `artifact_dir` validation. Direct combined packets remain parent-style, while prepared combined contexts remain task/blind child-only packets. |
| `quality_runner.review_report` | `application.review_reporting` | Finding normalization and report construction have one owner; the v1 serializer remains a separate reader/writer boundary. |

Internal CLI and MCP consumers now call application-owned audit, verification,
and journey services directly. Root workflow modules remain public façades only.
Application-owned workflow modules must not import root workflow, compatibility,
or CLI adapter modules; `tests/test_compatibility_boundaries.py` enforces that
direction. The same test ensures Fresh Review no longer depends on the root
review-context, review-types, or review-report façades.

The repository certifier, scanner contracts, and review-packet compatibility
surfaces are intentionally outside this extraction. They retain their existing
public paths until their own migration contract is complete.
