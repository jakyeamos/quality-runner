from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, cast

PERFORMANCE_SCHEMA = "quality-runner-web-performance-evidence/v1"
METRICS = {"lcp_ms", "inp_ms", "cls", "js_transfer_bytes"}
SCENARIO_FIELDS = {"route", "journey", "device", "network", "cpu", "cache", "dataset"}


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonnegative_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.utcoffset() is not None else None


def valid_scenario(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    scenario = cast(dict[str, Any], value)
    return (
        set(scenario) == SCENARIO_FIELDS
        and all(nonempty(item) for item in scenario.values())
        and scenario["device"] in {"mobile", "desktop"}
        and scenario["cache"] in {"cold", "warm"}
        and scenario["route"].startswith("/")
    )


def parse_performance_budgets(value: object) -> tuple[list[dict[str, Any]], list[str]]:
    if value is None:
        return [], []
    if not isinstance(value, list):
        return [], ["performance_budgets must be an array of tables"]
    budgets: list[dict[str, Any]] = []
    errors: list[str] = []
    identifiers: set[str] = set()
    for index, raw in enumerate(cast(list[object], value)):
        error = _budget_error(raw)
        if error:
            errors.append(f"performance_budgets[{index}]: {error}")
            continue
        budget = cast(dict[str, Any], raw)
        identifier = str(budget["id"])
        if identifier in identifiers:
            errors.append(f"performance_budgets has duplicate id {identifier}")
        identifiers.add(identifier)
        budgets.append(dict(budget))
    return budgets, errors


def _budget_error(value: object) -> str | None:
    if not isinstance(value, dict):
        return "each budget must be a table"
    budget = cast(dict[str, Any], value)
    required = {
        "id",
        "metric",
        "maximum",
        "statistic",
        "min_samples",
        "max_age_hours",
        "policy",
        "owner",
        "rationale",
        "method",
        "scenario",
    }
    if set(budget) != required:
        return "budget fields must match the documented contract"
    for field in ("id", "owner", "rationale"):
        if not nonempty(budget[field]):
            return f"{field} must be a non-empty string"
    if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", budget["id"]) is None:
        return "id must be an alphanumeric identifier"
    if not isinstance(budget["metric"], str) or budget["metric"] not in METRICS:
        return "unsupported metric"
    if not nonnegative_number(budget["maximum"]):
        return "maximum must be a finite non-negative number"
    if budget["metric"] == "js_transfer_bytes" and not isinstance(budget["maximum"], int):
        return "js_transfer_bytes maximum must be an integer"
    for field, allowed in (
        ("statistic", ("median", "max")),
        ("policy", ("warn", "block")),
        ("method", ("navigation", "interaction")),
    ):
        if budget[field] not in allowed:
            return f"unsupported {field}"
    count = budget["min_samples"]
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 1000:
        return "min_samples must be an integer between 1 and 1000"
    if not nonnegative_number(budget["max_age_hours"]) or budget["max_age_hours"] <= 0:
        return "max_age_hours must be a positive finite number"
    if not valid_scenario(budget["scenario"]):
        return "scenario must declare route, journey, device, network, cpu, cache and dataset"
    if budget["metric"] == "inp_ms" and budget["method"] != "interaction":
        return "INP requires interaction evidence; navigation and TBT are not INP"
    return None


def performance_evidence_error(value: object) -> str | None:
    if not isinstance(value, dict):
        return "Performance evidence must be an object."
    payload = cast(dict[str, Any], value)
    if set(payload) != {"schema", "observed_at", "target", "tool", "command", "measurements"}:
        return "Performance evidence fields must match the documented contract."
    if payload["schema"] != PERFORMANCE_SCHEMA:
        return f"Performance evidence must use {PERFORMANCE_SCHEMA}."
    if timestamp(payload["observed_at"]) is None:
        return "observed_at must be an ISO timestamp with a timezone."
    target = payload["target"]
    if not isinstance(target, dict):
        return "A production build target is required."
    target = cast(dict[str, Any], target)
    if (
        set(target) != {"commit", "build_mode", "build_id"}
        or target.get("build_mode") != "production"
        or not isinstance(target.get("commit"), str)
        or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", str(target.get("commit"))) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(target.get("build_id"))) is None
    ):
        return "Target requires an exact commit, production build_mode and sha256 build_id."
    tool = payload["tool"]
    if (
        not isinstance(tool, dict)
        or set(cast(dict[str, Any], tool)) != {"name", "version"}
        or not all(nonempty(item) for item in cast(dict[str, Any], tool).values())
        or not nonempty(payload["command"])
    ):
        return "Producer name, version and repeatable command are required."
    raw = payload["measurements"]
    if not isinstance(raw, list) or not 1 <= len(cast(list[object], raw)) <= 1000:
        return "measurements must contain between 1 and 1000 records."
    seen: set[str] = set()
    for item in cast(list[object], raw):
        error = _measurement_error(item)
        if error:
            return error
        record = cast(dict[str, Any], item)
        identifier = str(record["budget_id"])
        if identifier in seen:
            return f"Duplicate measurement for budget {identifier}."
        seen.add(identifier)
    return None


def _measurement_error(value: object) -> str | None:
    if not isinstance(value, dict):
        return "Each measurement must be an object."
    record = cast(dict[str, Any], value)
    if set(record) != {"budget_id", "metric", "method", "scenario", "samples"}:
        return "Measurement fields must match the documented contract."
    if (
        not nonempty(record["budget_id"])
        or not isinstance(record["metric"], str)
        or record["metric"] not in METRICS
        or record["method"] not in ("navigation", "interaction")
        or not valid_scenario(record["scenario"])
    ):
        return "Measurement requires a supported lab metric, method and complete scenario."
    if record["metric"] == "inp_ms" and record["method"] != "interaction":
        return "INP requires observed interactions; navigation and TBT cannot substitute."
    samples = record["samples"]
    if (
        not isinstance(samples, list)
        or not 1 <= len(cast(list[object], samples)) <= 1000
        or not all(nonnegative_number(item) for item in cast(list[object], samples))
    ):
        return "Samples must be a bounded list of finite non-negative numbers."
    if record["metric"] == "js_transfer_bytes" and not all(
        isinstance(item, int) for item in cast(list[object], samples)
    ):
        return "JavaScript transfer samples must be integer bytes."
    return None
