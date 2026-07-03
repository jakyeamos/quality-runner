from __future__ import annotations

import hashlib
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


def test_nested_ternary_rule_ignores_typescript_non_ternary_question_marks(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "src" / "syntax.ts",
        "\n".join(
            [
                "type Status = 'open' | 'closed' | 'pending';",
                "type Maybe<T> = T | null | undefined;",
                "const label = input?.profile?.name ?? fallback ?? 'Unknown';",
                "const matcher = /open|closed|pending/;",
                "const groupMatcher = /^(?:open|closed)$/;",
                "const optional = input?.profile?.name ? 'Known' : 'Unknown';",
                "const actual = items ? items.length ? 'a' : 'b' : 'c';",
            ]
        ),
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})
    nested = [finding for finding in result["findings"] if finding["rule_id"] == "nested-ternary"]

    assert [finding["line"] for finding in nested] == [7]


def test_code_quality_scan_detects_trpc_and_zod_patterns_outside_fixed_api_paths(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "src" / "server" / "router.ts",
        "\n".join(
            [
                "import { TRPCError } from '@trpc/server';",
                "export const route = publicProcedure.query(() => true);",
                "const name = z.string();",
                "throw new TRPCError({ code: 'BAD_REQUEST' });",
            ]
        ),
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    rules = {finding["rule_id"] for finding in result["findings"]}
    assert {
        "bare-trpc-error",
        "raw-free-text-z-string",
        "uninstrumented-trpc-procedure",
    } <= rules
    assert all("@soundscape/" not in finding["verification"] for finding in result["findings"])


def test_code_quality_scan_detects_ui_api_security_and_bundle_rules(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "apps" / "web" / "src" / "page.tsx",
        "\n".join(
            [
                "export function Page({ user, items, onOpen }) {",
                "  const result = useQuery({ queryKey: ['items'], queryFn: () => fetch('/api/items') });",
                "  return <main>",
                "    <div onClick={onOpen}>Open</div>",
                "    <button><Search /></button>",
                '    <img src="/avatar.png" />',
                "    <div tabIndex={3}>Bad focus</div>",
                "    <p>Lorem ipsum placeholder</p>",
                "    <Panel user={user} /><Sidebar user={user} /><Tray user={user} /><Footer user={user} />",
                "    {items.map((item) => <Row key={item.id} item={item} />)}",
                "  </main>;",
                "}",
            ]
        ),
    )
    _write(
        tmp_path / "apps" / "web" / "src" / "hero.tsx",
        'export const Hero = () => <Image className="hero" src="/hero.png" loading="lazy" />;\n',
    )
    _write(
        tmp_path / "apps" / "web" / "src" / "styles.css",
        ".bad { padding: 13px; outline: none; }\n.utility { margin-top: 2.3rem; }\n",
    )
    _write(
        tmp_path / "apps" / "web" / "src" / "app" / "api" / "items" / "route.ts",
        "\n".join(
            [
                "export async function POST(request: Request) {",
                "  const body = await request.json();",
                "  const message = `GitHub token request failed with ${body.status}`;",
                "  const query = `SELECT * FROM users WHERE id = ${body.id}`;",
                "  eval(body.code);",
                "  exec(`git ${body.arg}`);",
                "  readFile(req.query.path);",
                "  return Response.json({ message: 'bad' }, { status: 400 });",
                "}",
                "export async function GET() {",
                "  const rows = await db.user.findMany();",
                '  cors({ origin: "*" });',
                "  return Response.json(rows);",
                "}",
            ]
        ),
    )
    bundle_lines = [
        f"const value{i} = '{hashlib.sha256(str(i).encode()).hexdigest()}';" for i in range(10000)
    ]
    _write(tmp_path / "dist" / "assets" / "main.js", "\n".join(bundle_lines))

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    sql_findings = [
        finding
        for finding in result["findings"]
        if finding["rule_id"] == "sql-string-interpolation"
    ]
    rules = {finding["rule_id"] for finding in result["findings"]}
    assert len(sql_findings) == 1
    assert "SELECT * FROM users" in sql_findings[0]["evidence"]
    assert {
        "nonsemantic-click-target",
        "icon-button-missing-label",
        "image-missing-alt",
        "image-missing-dimensions",
        "hero-image-lazy-loading",
        "positive-tabindex",
        "removed-focus-outline",
        "off-scale-spacing",
        "placeholder-copy",
        "missing-loading-state",
        "missing-error-state",
        "missing-empty-state",
        "deep-prop-drilling",
        "api-route-missing-boundary-validation",
        "list-endpoint-missing-pagination",
        "inconsistent-error-envelope",
        "sql-string-interpolation",
        "wildcard-cors-origin",
        "eval-user-code",
        "user-controlled-shell-command",
        "user-controlled-file-path",
        "large-js-bundle-artifact",
    } <= rules


def test_code_quality_scan_avoids_dogfood_precision_false_positives(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "apps" / "web" / "src" / "component.tsx",
        "\n".join(
            [
                '"use client";',
                "const navItems = [{ label: 'Home' }];",
                "const features = [{ label: 'Fast' }];",
                "export function Component({ items }) {",
                "  const result = useQuery({ queryKey: ['items'], queryFn: () => fetch('/api/items') });",
                "  if (result.isLoading) return <Skeleton />;",
                '  if (result.error) return <div role="alert">Failed</div>;',
                "  return <main>",
                "    <Image",
                "      alt={items[0].title}",
                '      className="aspect-video"',
                "      height={336}",
                "      src={items[0].image}",
                "      width={640}",
                "    />",
                '    <input placeholder="Email" />',
                "    <nav>{navItems.map((item) => <a key={item.label}>{item.label}</a>)}</nav>",
                "    <section>{features.map((feature) => <p key={feature.label}>{feature.label}</p>)}</section>",
                "    {Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} />)}",
                "    {items.map((item) => <Row key={item.id} item={item} />)}",
                "    <p>sample text</p>",
                "  </main>;",
                "}",
            ]
        ),
    )
    _write(
        tmp_path / "apps" / "web" / "src" / "styles.css",
        "input::placeholder { color: gray; }\n",
    )
    _write(
        tmp_path / "apps" / "web" / "src" / "app" / "api" / "user" / "route.ts",
        "\n".join(
            [
                "export async function GET() {",
                "  const user = await getUser();",
                "  return Response.json(user);",
                "}",
            ]
        ),
    )
    _write(
        tmp_path / "apps" / "web" / "src" / "app" / "api" / "items" / "route.ts",
        "\n".join(
            [
                "export async function GET() {",
                "  const rows = await db.item.findMany();",
                "  return Response.json(rows);",
                "}",
            ]
        ),
    )
    _write(
        tmp_path / "apps" / "web" / "src" / "stream.ts",
        "\n".join(
            [
                "export async function read(reader) {",
                "  while (true) {",
                "    const { done } = await reader.read();",
                "    if (done) break;",
                "  }",
                "}",
            ]
        ),
    )
    _write(
        tmp_path / "apps" / "web" / "src" / "interceptors.ts",
        "\n".join(
            [
                "export async function apply(config, interceptors) {",
                "  for (const fn of interceptors.request._fns) {",
                "    config = await fn(config);",
                "  }",
                "  return config;",
                "}",
            ]
        ),
    )
    _write(
        tmp_path / "apps" / "web" / "src" / "component.spec.ts",
        "\n".join(
            [
                "test('tabs', async ({ page }) => {",
                "  for (const tab of tabs) {",
                "    await expect(page.getByRole('tab', { name: tab })).toBeVisible();",
                "  }",
                "});",
            ]
        ),
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    findings_by_rule = {}
    for finding in result["findings"]:
        findings_by_rule.setdefault(finding["rule_id"], []).append(finding)

    assert "image-missing-alt" not in findings_by_rule
    assert "image-missing-dimensions" not in findings_by_rule
    assert len(findings_by_rule["placeholder-copy"]) == 1
    assert "sample text" in findings_by_rule["placeholder-copy"][0]["evidence"]
    assert len(findings_by_rule["missing-empty-state"]) == 1
    assert "items.map" in findings_by_rule["missing-empty-state"][0]["evidence"]
    assert len(findings_by_rule["list-endpoint-missing-pagination"]) == 1
    assert findings_by_rule["list-endpoint-missing-pagination"][0]["file"].endswith(
        "api/items/route.ts"
    )
    await_findings = findings_by_rule["await-in-loop"]
    assert all("reader.read" not in finding["evidence"] for finding in await_findings)
    assert all("expect(" not in finding["evidence"] for finding in await_findings)
    assert any(finding["severity"] == "observation" for finding in await_findings)


def test_code_quality_scan_detects_ponytail_debt_rules(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "package.json",
        '{"dependencies": {"uuid": "^9.0.0"}}\n',
    )
    _write(
        tmp_path / "src" / "service.ts",
        "\n".join(
            [
                "import { v4 as uuidv4 } from 'uuid';",
                "interface PaymentGateway { charge(): void }",
                "class StripeGateway implements PaymentGateway { charge() {} }",
                "abstract class Exporter { abstract run(): void }",
                "class CsvExporter extends Exporter { run() {} }",
                "class ReportFactory {",
                "  create() { return new CsvExporter(); }",
                "}",
                "export function loadUser(id: string) {",
                "  return userRepo.load(id);",
                "}",
                "export function randomId() {",
                "  return Math.random().toString(36).slice(2);",
                "}",
                "export function parseQuery(query: string) {",
                "  return query.split('&').map((part) => part.split('='));",
                "}",
                "function debounce(fn) {",
                "  let timeout;",
                "  return (...args) => { clearTimeout(timeout); timeout = setTimeout(() => fn(...args), 100); };",
                "}",
                "const flag = process.env.EXPERIMENT_ONE;",
                "void uuidv4;",
            ]
        ),
    )
    _write(
        tmp_path / "src" / "csv_tools.py",
        "def parse_csv(line):\n    return line.split(',')\n",
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    ponytail_findings = [
        finding for finding in result["findings"] if finding["category"] == "ponytail"
    ]
    rules = {finding["rule_id"] for finding in ponytail_findings}
    assert {
        "single-implementation-abstraction",
        "single-product-factory",
        "pass-through-wrapper",
        "undocumented-env-flag",
        "single-use-trivial-dependency",
        "hand-rolled-uuid",
        "hand-rolled-url-parser",
        "hand-rolled-debounce",
        "hand-rolled-csv-parser",
    } <= rules
    assert {finding["remediation_bucket"] for finding in ponytail_findings} >= {
        "Ponytail debt: native",
        "Ponytail debt: shrink",
        "Ponytail debt: stdlib",
        "Ponytail debt: yagni",
    }


def test_code_quality_fingerprint_is_stable_when_line_number_changes(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    source = tmp_path / "src" / "index.ts"
    _write(source, "const value: any = {};\n")
    first = create_code_quality_scan(tmp_path, scan={"run_id": "first"}, config={})
    first_fingerprint = next(
        finding["fingerprint"]
        for finding in first["findings"]
        if finding["rule_id"] == "explicit-any"
    )

    source.write_text("// inserted header\nconst value: any = {};\n", encoding="utf-8")
    second = create_code_quality_scan(tmp_path, scan={"run_id": "second"}, config={})
    second_fingerprint = next(
        finding["fingerprint"]
        for finding in second["findings"]
        if finding["rule_id"] == "explicit-any"
    )

    assert second_fingerprint == first_fingerprint


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


def test_code_quality_scan_applies_configured_scan_exclusions(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / ".planning" / "remediation.ts", "const planned: any = {};\n")
    _write(tmp_path / "scripts" / "generated-report.ts", "const report: any = {};\n")
    _write(tmp_path / "src" / "index.ts", "const value: any = {};\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={"scan_exclusions": [".planning", "scripts/generated-*"]},
    )

    scanned_paths = {item["path"] for item in result["accountability"]}
    skipped = {item["path"]: item["reason"] for item in result["skipped_files"]}
    finding_files = {finding["file"] for finding in result["findings"]}

    assert scanned_paths == {"src/index.ts"}
    assert skipped[".planning"] == "scan exclusion"
    assert skipped["scripts/generated-report.ts"] == "scan exclusion"
    assert finding_files == {"src/index.ts"}


def test_code_quality_scan_applies_root_gitignore_exclusions(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    (tmp_path / ".gitignore").write_text("Ignored Dashboard/\n", encoding="utf-8")
    _write(tmp_path / "Ignored Dashboard" / "page.tsx", "const ignored: any = {};\n")
    _write(tmp_path / "src" / "index.ts", "const value: any = {};\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={},
    )

    scanned_paths = {item["path"] for item in result["accountability"]}
    skipped = {item["path"]: item["reason"] for item in result["skipped_files"]}
    finding_files = {finding["file"] for finding in result["findings"]}

    assert scanned_paths == {"src/index.ts"}
    assert skipped["Ignored Dashboard"] == "scan exclusion"
    assert finding_files == {"src/index.ts"}


def test_code_quality_scan_excludes_hidden_operational_dirs_by_default(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    for directory in (".aios", ".planning", ".superpowers", ".tracker"):
        _write(tmp_path / directory / "notes.ts", "const hidden: any = {};\n")
    _write(tmp_path / "src" / "index.ts", "const value: any = {};\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={},
    )

    scanned_paths = {item["path"] for item in result["accountability"]}
    skipped = {item["path"]: item["reason"] for item in result["skipped_files"]}
    finding_files = {finding["file"] for finding in result["findings"]}

    assert scanned_paths == {"src/index.ts"}
    assert skipped == {
        ".aios": "scan exclusion",
        ".planning": "scan exclusion",
        ".superpowers": "scan exclusion",
        ".tracker": "scan exclusion",
    }
    assert finding_files == {"src/index.ts"}


def test_code_quality_scan_include_ignored_paths_overrides_scan_exclusions(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / "docs" / "example.ts", "const documented: any = {};\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={"structural_scan": {"include_ignored_paths": ["docs"]}},
    )

    assert {item["path"] for item in result["accountability"]} == {"docs/example.ts"}
    assert {finding["file"] for finding in result["findings"]} == {"docs/example.ts"}


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


def test_code_quality_scan_ignores_shadow_vendor_cache_and_build_variants(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / ".aios" / "shadow-worktrees" / "copy" / "src" / "shadow.ts",
        "const shadow: any = {};\n",
    )
    _write(
        tmp_path / ".worktrees" / "feature-copy" / "src" / "copy.ts",
        "const copy: any = {};\n",
    )
    _write(
        tmp_path / "apps" / "dashboard" / ".next-broken-20260323-1" / "server" / "_error.js",
        "eval(userInput);\n",
    )
    _write(
        tmp_path
        / ".tmp"
        / "uv-bootstrap"
        / "lib"
        / "python3.14"
        / "site-packages"
        / "pip"
        / "x.py",
        "value = any([True])\n",
    )
    _write(
        tmp_path / "packages" / "web" / "node_modules" / "lib" / "index.ts",
        "const dependency: any = {};\n",
    )
    _write(tmp_path / ".pnpm-store" / "index.ts", "const store: any = {};\n")
    _write(tmp_path / "data" / "fixture.json", '{"value": "not source"}\n')
    _write(tmp_path / "logs" / "run.md", "const logged: any = {};\n")
    _write(tmp_path / "staging" / "takeout" / "raw.md", "const staged: any = {};\n")
    _write(tmp_path / "tmcp-benchmark" / "tasks" / "case.md", "const benchmark: any = {};\n")
    _write(tmp_path / "apps" / "web" / "public" / "dashboard_data" / "row.json", "{}\n")
    _write(tmp_path / "src" / "data" / "model.ts", "const model: any = {};\n")
    _write(tmp_path / "src" / "index.ts", "const value: any = {};\n")

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    scanned_paths = {item["path"] for item in result["accountability"]}
    skipped = {item["path"]: item["reason"] for item in result["skipped_files"]}
    finding_files = {finding["file"] for finding in result["findings"]}

    assert scanned_paths == {"src/data/model.ts", "src/index.ts"}
    assert skipped[".aios"] == "scan exclusion"
    assert skipped[".worktrees"] == "ignored directory"
    assert skipped["apps/dashboard/.next-broken-20260323-1"] == "ignored directory"
    assert skipped[".tmp"] == "ignored directory"
    assert skipped[".pnpm-store"] == "ignored directory"
    assert skipped["data"] == "ignored directory"
    assert skipped["logs"] == "ignored directory"
    assert skipped["staging"] == "ignored directory"
    assert skipped["tmcp-benchmark"] == "ignored directory"
    assert skipped["packages/web/node_modules"] == "ignored directory"
    assert skipped["apps/web/public"] == "ignored directory"
    assert finding_files == {"src/data/model.ts", "src/index.ts"}


def test_code_quality_scan_reports_estimated_cost_for_skipped_paths(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    for index in range(3):
        _write(tmp_path / "data" / f"row-{index}.json", "{}\n")
    _write(tmp_path / "src" / "index.ts", "const value: any = {};\n")

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})
    skipped = {item["path"]: item for item in result["skipped_files"]}

    assert skipped["data"]["estimated_text_files"] == 3
    assert skipped["data"]["estimated_scan_seconds"] > 0
    assert skipped["data"]["include_config_hint"] == (
        '[quality_runner.structural_scan] include_ignored_paths = ["data"]'
    )
    assert result["summary"]["skipped_estimated_text_files"] == 3
    assert result["summary"]["skipped_estimated_scan_seconds"] > 0


def test_code_quality_scan_stops_at_configured_file_budget(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    for index in range(5):
        _write(tmp_path / "src" / f"file-{index}.ts", f"const value{index}: any = {{}};\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-budget"},
        config={"structural_scan": {"max_text_files": 2}},
    )

    scanned_paths = [item["path"] for item in result["accountability"]]
    skipped = {item["path"]: item["reason"] for item in result["skipped_files"]}

    assert scanned_paths == ["src/file-0.ts", "src/file-1.ts"]
    assert skipped == {
        "src/file-2.ts": "scan budget exceeded",
        "src/file-3.ts": "scan budget exceeded",
        "src/file-4.ts": "scan budget exceeded",
    }
    assert result["summary"]["scan_budget"] == {
        "max_text_files": 2,
        "scanned_text_files": 2,
        "budget_exceeded": True,
        "skipped_text_files": 3,
    }


def test_code_quality_scan_can_include_default_ignored_paths(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / "data" / "model.ts", "const included: any = {};\n")
    _write(tmp_path / "src" / "index.ts", "const value: any = {};\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={"structural_scan": {"include_ignored_paths": ["data"]}},
    )

    scanned_paths = {item["path"] for item in result["accountability"]}
    finding_files = {finding["file"] for finding in result["findings"]}

    assert {"data/model.ts", "src/index.ts"} <= scanned_paths
    assert "data/model.ts" in finding_files
    assert all(item["path"] != "data" for item in result["skipped_files"])


def test_quality_runner_source_files_stay_under_default_large_file_threshold() -> None:
    from quality_runner.code_quality import DEFAULT_LARGE_FILE_LINES

    repo_root = Path(__file__).resolve().parents[1]
    oversized: dict[str, int] = {}
    for path in sorted((repo_root / "quality_runner").rglob("*.py")):
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > DEFAULT_LARGE_FILE_LINES:
            oversized[path.relative_to(repo_root).as_posix()] = line_count

    assert oversized == {}
