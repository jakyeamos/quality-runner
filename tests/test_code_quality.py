from __future__ import annotations

from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_code_quality_scan_reports_deterministic_rule_groups_and_fingerprints(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "packages" / "api" / "src" / "routers" / "artist.ts",
        "\n".join(
            [
                "import { publicProcedure } from '../trpc';",
                "import { TRPCError } from '@trpc/server';",
                "const name = z.string();",
                "export function repeated(value: string) {",
                "  const local = value.trim();",
                "  return local.toUpperCase();",
                "}",
                "export function repeatedAgain(other: string) {",
                "  const local = other.trim();",
                "  return local.toUpperCase();",
                "}",
                "export async function run(items: string[]) {",
                "  try {",
                "    if (items.length) {",
                "      for (const item of items) {",
                "        if (item) {",
                "          await Promise.resolve(item);",
                "        }",
                "      }",
                "    }",
                "  } catch {}",
                "  throw new TRPCError({ code: 'BAD_REQUEST' });",
                "}",
                "export const route = publicProcedure.query(() => true);",
                "const typed: any = {};",
                "// TODO: remove this",
                "const env = process.env.SECRET!;",
                "const value = items ? items.length ? 'a' : 'b' : 'c';",
            ]
        ),
    )
    _write(
        tmp_path / "packages" / "web" / "src" / "app" / "page.tsx",
        "\n".join(
            [
                "import { trpc } from '@/lib/trpc';",
                "export default function Page() {",
                "  const user = trpc.user.me.useQuery();",
                '  return <div className="card"><div className="card">Nested</div></div>;',
                "}",
            ]
        ),
    )
    _write(
        tmp_path / "packages" / "web" / "src" / "app" / "styles.css",
        "\n".join(
            [
                ".hero { background: linear-gradient(red, blue); background-clip: text; color: transparent; }",
                ".grid { background-image: linear-gradient(#eee 1px, transparent 1px), linear-gradient(90deg, #eee 1px, transparent 1px); }",
                ".callout { border-left: 6px solid red; }",
                ".panel { border-radius: 32px; z-index: 9999; opacity: 0; }",
            ]
        ),
    )
    _write(
        tmp_path / "packages" / "web" / "src" / "button.test.ts",
        "test('weak', () => { expect(true).toBe(true); console.log('noise'); });\n",
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    assert result["schema"] == "quality-runner-code-quality-scan-v0.1"
    rules = {finding["rule_id"] for finding in result["findings"]}
    assert {
        "explicit-any",
        "silent-catch",
        "bare-trpc-error",
        "raw-free-text-z-string",
        "uninstrumented-trpc-procedure",
        "env-non-null-assertion",
        "todo-comment",
        "nested-ternary",
        "deep-nesting",
        "await-in-loop",
        "page-data-access",
        "weak-test-assertion",
        "console-output",
        "gradient-text",
        "decorative-grid-background",
        "side-stripe-border",
        "excessive-border-radius",
        "arbitrary-z-index",
        "nested-card-markup",
        "risky-hidden-reveal",
        "near-duplicate-function",
    } <= rules
    assert result["duplicate_clusters"]
    assert all(finding["fingerprint"] for finding in result["findings"])
    assert result["summary"]["findings_by_category"]["ui_structural"] >= 6


def test_code_quality_scan_respects_config_and_generated_ignores(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / "dist" / "bundle.ts", "const value: any = {};\n")
    _write(tmp_path / "src" / "index.ts", "const value: any = {};\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={
            "structural_scan": {
                "disabled_rule_groups": ["harden"],
                "large_file_lines": 10,
                "fat_router_lines": 10,
            }
        },
    )

    assert not result["findings"]
    assert any(item["path"] == "dist" for item in result["skipped_files"])


def test_code_quality_scan_ignores_generated_build_large_tests_and_non_frontend(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / "src" / "generated" / "client.ts", "const generated: any = {};\n")
    _write(tmp_path / "src" / "client.generated.ts", "const generated: any = {};\n")
    _write(tmp_path / "build" / "bundle.ts", "const bundled: any = {};\n")
    _write(tmp_path / "tests" / "test_large.py", "\n".join(["assert True"] * 12))
    _write(tmp_path / "src" / "service.py", "\n".join(['declared = {"ok": any([True])}'] * 12))

    result = create_code_quality_scan(
        tmp_path,
        scan={
            "run_id": "scan-001",
            "generated_code": [{"path": "src/generated", "evidence": "generated directory"}],
        },
        config={"structural_scan": {"large_file_lines": 10}},
    )

    scanned_paths = {item["path"] for item in result["accountability"]}
    skipped_paths = {item["path"] for item in result["skipped_files"]}
    rules = {finding["rule_id"] for finding in result["findings"]}

    assert {"src/service.py", "tests/test_large.py"} <= scanned_paths
    assert "src/generated" in skipped_paths
    assert "src/client.generated.ts" in skipped_paths
    assert "build" in skipped_paths
    assert "explicit-any" not in rules
    assert "large-source-file" in rules
    assert all(finding["file"] != "tests/test_large.py" for finding in result["findings"])
    assert result["summary"]["findings_by_category"]["ui_structural"] == 0


def test_quality_runner_source_files_stay_under_default_large_file_threshold() -> None:
    from quality_runner.code_quality import DEFAULT_LARGE_FILE_LINES

    repo_root = Path(__file__).resolve().parents[1]
    oversized: dict[str, int] = {}
    for path in sorted((repo_root / "quality_runner").rglob("*.py")):
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > DEFAULT_LARGE_FILE_LINES:
            oversized[path.relative_to(repo_root).as_posix()] = line_count

    assert oversized == {}
