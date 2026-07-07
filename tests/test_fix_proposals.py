from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_support.quality_runner_fixtures import write_complete_js_fixture

from quality_runner.fix_proposals import propose_fix
from quality_runner.workflow import run_payload


def test_propose_fix_writes_structural_group_proposals(tmp_path: Path) -> None:
    write_complete_js_fixture(tmp_path)
    source = tmp_path / "src" / "app" / "page.tsx"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "\n".join(
            [
                "import { trpc } from '@/lib/trpc';",
                "export default function Page() {",
                "  const user = trpc.user.me.useQuery();",
                "  const first: any = user.data;",
                "  const second: any = user.error;",
                '  return <main><div className="card"><div className="card">Nested</div></div></main>;',
                "}",
            ]
        ),
        encoding="utf-8",
    )
    run_payload(repo_root=tmp_path, run_id="proposal-run", profile="default")

    result = propose_fix(
        repo_root=tmp_path,
        run_id="proposal-run",
        finding_group="remediate-structural-src-app-page-tsx",
        proposal_id="proposal-test-001",
    )
    payload = result["fix_proposals"]
    path = Path(result["fix_proposals_path"])

    assert result["schema"] == "quality-runner-fix-propose-result-v0.1"
    assert result["status"] == "proposed"
    assert result["implementation_allowed"] is False
    assert payload["applied"] is False
    assert payload["implementation_allowed"] is False
    assert payload["proposal_id"] == "proposal-test-001"
    assert payload["finding_group"] == "remediate-structural-src-app-page-tsx"
    assert payload["proposals"]
    assert all(proposal["applied"] is False for proposal in payload["proposals"])
    assert all(proposal["kind"] == "instruction" for proposal in payload["proposals"])
    assert all(proposal["checksum"].startswith("sha256:") for proposal in payload["proposals"])
    assert payload["checksum"].startswith("sha256:")
    assert path.exists()


def test_propose_fix_filters_finding_ids(tmp_path: Path) -> None:
    write_complete_js_fixture(tmp_path)
    source = tmp_path / "src" / "app" / "page.tsx"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("const value: any = 1;\n", encoding="utf-8")
    run_payload(repo_root=tmp_path, run_id="proposal-filter", profile="default")
    handoff = json.loads(
        (tmp_path / ".quality-runner/runs/proposal-filter/agent-handoff.json").read_text()
    )
    finding_id = handoff["next_slice"]["findings"][0]["id"]

    result = propose_fix(
        repo_root=tmp_path,
        run_id="proposal-filter",
        finding_group=handoff["next_slice"]["id"],
        finding_ids=[finding_id],
    )

    assert len(result["fix_proposals"]["proposals"]) == 1
    assert result["fix_proposals"]["proposals"][0]["finding_id"] == finding_id


def test_propose_fix_rejects_unknown_finding_group(tmp_path: Path) -> None:
    write_complete_js_fixture(tmp_path)
    run_payload(repo_root=tmp_path, run_id="proposal-missing", profile="default")

    with pytest.raises(ValueError, match="finding group does not exist"):
        propose_fix(
            repo_root=tmp_path,
            run_id="proposal-missing",
            finding_group="missing-slice",
        )


def test_propose_fix_requires_existing_run(tmp_path: Path) -> None:
    write_complete_js_fixture(tmp_path)

    with pytest.raises(FileNotFoundError, match="run does not exist"):
        propose_fix(
            repo_root=tmp_path,
            run_id="missing-run",
            finding_group="remediate-any",
        )
