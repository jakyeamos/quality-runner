from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import date
from pathlib import Path


def _load_checker():
    path = Path(__file__).parents[1] / "scripts" / "check_environment_contract.py"
    spec = importlib.util.spec_from_file_location("environment_contract", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load environment contract checker")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = _load_checker()


def _write_contract(root: Path, *, adapter: bool = True, route: bool = True) -> None:
    (root / ".agents/context").mkdir(parents=True)
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".tracker").mkdir()
    (root / "AGENTS.md").write_text(
        "approval target credential remote\n[context](.agents/context/README.md)\n",
        encoding="utf-8",
    )
    index_markers = "minimum context; do not recursively load; current truth" if route else ""
    (root / ".agents/context/README.md").write_text(
        f"last_reviewed: 2026-07-22\n{index_markers}\n[packet](architecture.md)\n",
        encoding="utf-8",
    )
    for packet in CHECKER.PACKETS:
        (root / ".agents/context" / packet).write_text("# packet\n", encoding="utf-8")
    for path in CHECKER.REQUIRED_FILES:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if path == "pyproject.toml":
            target.write_text(
                "[project.scripts]\nquality-runner='quality_runner.cli:main'\nqr='quality_runner.cli:main'\n"
                "[tool.basedpyright]\ntypeCheckingMode='standard'\n",
                encoding="utf-8",
            )
        elif path == ".pre-cr.json":
            adapters = (
                '[{"name":"environment-contract","command":"python3 scripts/check_environment_contract.py",'
                '"required":true}]'
                if adapter
                else "[]"
            )
            target.write_text(f'{{"qualityAdapters":{adapters}}}\n', encoding="utf-8")
        elif path == ".github/workflows/ci.yml":
            target.write_text(
                "steps:\n  - run: python scripts/check_environment_contract.py\n", encoding="utf-8"
            )
        else:
            target.write_text("# fixture\n", encoding="utf-8")


class EnvironmentContractTests(unittest.TestCase):
    def test_repository_contract_passes(self) -> None:
        root = Path(__file__).parents[1]
        result = CHECKER.validate(root, date(2026, 7, 22), tracked_paths=[])
        self.assertEqual(result["status"], "pass")

    def test_missing_packet_and_broken_link_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_contract(root)
            (root / ".agents/context/README.md").write_text(
                "last_reviewed: 2026-07-22\nminimum context current truth\n[missing](missing.md)\n",
                encoding="utf-8",
            )
            (root / ".agents/context/architecture.md").unlink()
            result = CHECKER.validate(root, date(2026, 7, 22), tracked_paths=[])
            self.assertEqual(result["status"], "fail")
            self.assertIn(
                "broken context link in .agents/context/README.md: missing.md", result["errors"]
            )
            self.assertIn("missing context packet: architecture.md", result["errors"])

    def test_stale_index_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_contract(root)
            index = root / ".agents/context/README.md"
            index.write_text(
                "last_reviewed: 2025-01-01\nminimum context current truth\n", encoding="utf-8"
            )
            result = CHECKER.validate(root, date(2026, 7, 22), tracked_paths=[])
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("context index is stale" in item for item in result["errors"]))

    def test_required_adapter_and_route_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_contract(root, adapter=False, route=False)
            result = CHECKER.validate(root, date(2026, 7, 22), tracked_paths=[])
            self.assertEqual(result["status"], "fail")
            self.assertIn(
                "required environment-contract pre-CR adapter is missing", result["errors"]
            )
            self.assertTrue(any("routing marker" in item for item in result["errors"]))

    def test_secret_path_guard_allows_examples(self) -> None:
        self.assertEqual(CHECKER.check_secret_paths([".env.example", ".env.template"]), [])
        self.assertEqual(
            CHECKER.check_secret_paths(["config/production.env", "keys/id_rsa"]),
            ["config/production.env", "keys/id_rsa"],
        )
