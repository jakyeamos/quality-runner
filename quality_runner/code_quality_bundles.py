from __future__ import annotations

import gzip
from pathlib import Path
from typing import cast

from quality_runner.code_quality_findings import _finding

DEFAULT_GZIPPED_JS_BUNDLE_BYTES = 200_000
JS_BUNDLE_DIRS = (
    ".next/static/chunks",
    "build/static/js",
    "dist/assets",
    "out/_next/static/chunks",
)
Finding = dict[str, object]


def bundle_budget_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for bundle_dir in JS_BUNDLE_DIRS:
        path = root / bundle_dir
        if not path.is_dir():
            continue
        for bundle in sorted(path.rglob("*.js")):
            if bundle.name.endswith(".map") or not bundle.is_file():
                continue
            gzipped_size = len(gzip.compress(bundle.read_bytes()))
            if gzipped_size <= DEFAULT_GZIPPED_JS_BUNDLE_BYTES:
                continue
            relative_path = bundle.relative_to(root).as_posix()
            findings.append(
                cast(
                    Finding,
                    _finding(
                        category="speed",
                        severity="observation",
                        confidence="medium",
                        file=relative_path,
                        line=1,
                        rule_id="large-js-bundle-artifact",
                        evidence=f"{gzipped_size} gzipped bytes",
                        expected_improvement=(
                            "Split initial routes, lazy-load heavy features, or remove unused dependencies."
                        ),
                        risk="Large initial JavaScript bundles delay load and interaction readiness.",
                        verification="Run bundle analysis and the relevant frontend build.",
                        remediation_bucket="frontend performance and bundle budget",
                    ),
                )
            )
    return findings
