from pathlib import Path

CONTRACT_PATH = Path(".pronto/behavior-assurance.json")
RECEIPT_DIRECTORY = Path(".quality-runner/behavior-assurance/receipts")
CONTRACT_SCHEMA = "pronto-behavior-assurance/v2"
LEGACY_CONTRACT_SCHEMA = "pronto-behavior-assurance/v1"
CONTRACT_SCHEMAS = {CONTRACT_SCHEMA, LEGACY_CONTRACT_SCHEMA}
RECEIPT_SCHEMA = "quality-runner-behavior-receipt/v1"
ASSESSMENT_SCHEMA = "quality-runner-behavior-assurance/v2"
TRACE_SCHEMA = "quality-runner-edge-trace/v1"
AUTOMATION_MODES = {"permanent", "on_demand", "manual"}
VERIFICATION_LEVELS = {
    "source": 0,
    "automated": 1,
    "direct_surface": 2,
    "independent": 3,
}
RESULT_STATUSES = {"passed", "failed", "blocked", "not_applicable"}
EDGE_CATEGORIES = {
    "input_and_encoding",
    "state_and_ordering",
    "repetition_and_idempotency",
    "timing_and_concurrency",
    "interruption_and_recovery",
    "resource_pressure",
    "authorization_and_session",
    "environment_and_cross_surface",
}
EDGE_RISKS = {"routine", "hostile"}
EDGE_SIDE_EFFECTS = {"none", "reversible", "destructive"}
EDGE_ENVIRONMENTS = {"local", "test", "preview", "staging"}
EDGE_SURFACES = {"ui", "native", "cli", "api", "workflow"}
EDGE_SENSITIVITIES = {"normal", "security_sensitive"}
MAX_FILE_BYTES = 250_000
MAX_TRACE_STEPS = 100
MAX_TRACE_REPLAY_ATTEMPTS = 3
MAX_SCENARIO_RECORDS = 500
