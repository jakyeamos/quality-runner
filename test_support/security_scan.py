from __future__ import annotations

from pathlib import Path

from quality_runner.config import load_repo_config
from quality_runner.discovery import inspect_repo
from quality_runner.security.scan import create_security_scan
from quality_runner.standards import compile_standards


def run_security_scan(repo: Path, config_text: str | None = None) -> dict:
    if config_text is not None:
        (repo / ".quality-runner.toml").write_text(config_text, encoding="utf-8")
    config = load_repo_config(repo)
    scan = inspect_repo(repo, run_id="sec-test", ci_checks=[], extra_warnings=[], config=config)
    standards = compile_standards(repo_root=repo, scan=scan, profile="default", config=config)
    return create_security_scan(repo, scan=scan, config=config, standards_packet=standards)
