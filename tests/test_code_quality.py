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
    test_console = next(
        finding
        for finding in result["findings"]
        if finding["category"] == "improve-tests" and finding["rule_id"] == "console-output"
    )
    assert test_console["suggested_disposition"] == "insufficient_evidence"


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
    _write(
        tmp_path / "tests" / "test_large.py",
        "\n".join(f"fixture_value_{index} = {index}" for index in range(12)),
    )
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
    large_file = next(
        finding for finding in result["findings"] if finding["rule_id"] == "large-source-file"
    )
    assert large_file["category"] == "debloat"
    assert large_file["confidence"] == "low"
    assert large_file["remediation_bucket"] == "debloat candidate review"
    assert "does not authorize deletion" in large_file["risk"]
    assert "must not narrow the read-only audit" in large_file["risk"]
    assert "duplicated engines" in large_file["expected_improvement"]
    assert result["summary"]["findings_by_category"]["debloat"] == 1
    assert not any(
        finding["rule_id"] == "large-source-file" and finding["category"] == "simplify"
        for finding in result["findings"]
    )
    assert all(finding["file"] != "tests/test_large.py" for finding in result["findings"])
    assert result["summary"]["findings_by_category"]["ui_structural"] == 0


def test_code_quality_scan_can_disable_debloat_candidates(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / "src" / "service.py", "\n".join(["value = 1"] * 12))

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={
            "structural_scan": {
                "disabled_rule_groups": ["debloat"],
                "large_file_lines": 10,
            }
        },
    )

    assert result["summary"]["findings_by_category"]["debloat"] == 0
    assert not any(finding["category"] == "debloat" for finding in result["findings"])


def test_fat_router_owns_overlapping_large_file_signal(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "src" / "routers" / "api.ts",
        "\n".join(f"const value{index} = {index};" for index in range(12)),
    )

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={"structural_scan": {"large_file_lines": 10, "fat_router_lines": 10}},
    )

    debloat_rules = [
        finding["rule_id"] for finding in result["findings"] if finding["category"] == "debloat"
    ]
    assert debloat_rules == ["fat-router"]
    fat_router = next(
        finding for finding in result["findings"] if finding["rule_id"] == "fat-router"
    )
    assert fat_router["confidence"] == "low"
    assert "legacy routes" in fat_router["expected_improvement"]


def test_test_quality_findings_are_bounded_and_include_remediation_dispositions(
    tmp_path: Path,
) -> None:
    from quality_runner.audit import _code_quality_findings
    from quality_runner.code_quality import create_code_quality_scan

    removed_test = "\n".join(
        [
            "test('retired graph stays gone', () => {",
            "  expect(screen.queryByText('Workspace activity')).not.toBeInTheDocument();",
            "});",
        ]
    )
    duplicate_body = "\n".join(
        [
            "test('saves the record', () => {",
            "  const result = saveRecord({ name: 'Ada' });",
            "  expect(result.name).toBe('Ada');",
            "});",
        ]
    )
    _write(tmp_path / "src" / "removed.test.tsx", removed_test)
    _write(
        tmp_path / "src" / "mixed-removed.test.tsx",
        "\n".join(
            [
                "test('retired redirect remains gone', () => {",
                "  expect(screen.queryByText('Legacy')).not.toBeInTheDocument();",
                "  expect(currentRoute()).toBe('/home');",
                "});",
            ]
        ),
    )
    _write(tmp_path / "src" / "duplicate-a.test.ts", duplicate_body)
    _write(tmp_path / "src" / "duplicate-b.test.ts", duplicate_body.replace("saves", "persists"))
    _write(
        tmp_path / "src" / "interaction.test.ts",
        "test('calls save', () => { save(); expect(save).toHaveBeenCalled(); });\n",
    )
    _write(tmp_path / "tests" / "test_tautology.py", "def test_value():\n    assert True\n")
    _write(
        tmp_path / "tests" / "test_removed_widget.py",
        "def test_removed_widget():\n    assert 'widget' not in rendered\n",
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})
    test_findings = {
        finding["rule_id"]: finding
        for finding in result["findings"]
        if finding["category"] == "improve-tests"
    }

    assert test_findings["removed-behavior-lock"]["suggested_disposition"] == ("delete_candidate")
    assert test_findings["exact-duplicate-test-body"]["suggested_disposition"] == "merge"
    assert test_findings["weak-test-assertion"]["suggested_disposition"] == "rewrite"
    assert all(finding["disposition_rationale"] for finding in test_findings.values())
    removed_files = {
        finding["file"]
        for finding in result["findings"]
        if finding["rule_id"] == "removed-behavior-lock"
    }
    assert removed_files == {"src/removed.test.tsx", "tests/test_removed_widget.py"}
    assert not any(
        finding["rule_id"] == "weak-test-assertion" and finding["file"] == "src/interaction.test.ts"
        for finding in result["findings"]
    )
    audit_findings = {finding["id"]: finding for finding in _code_quality_findings(result)}
    assert (
        audit_findings["structural-improve-tests-removed-behavior-lock"]["suggested_disposition"]
        == "delete_candidate"
    )


def test_test_quality_subtypes_flag_tautologies_without_flagging_interaction_contracts(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "src" / "tautologies.test.ts",
        "\n".join(
            [
                "test('literal', () => {",
                "  expect(true).toBe(true);",
                "});",
                "test('self comparison', () => {",
                "  expect(value).toEqual(value);",
                "});",
                "test('derived expected', () => {",
                "  const actual = service.load();",
                "  const expected_value = actual;",
                "  expect(actual).toEqual(expected_value);",
                "});",
                "test('mock echo', () => {",
                "  repo.save(item);",
                "  const recorded = repo.save.mock.calls[0][0];",
                "  expect(repo.save).toHaveBeenCalledWith(recorded);",
                "});",
                "test('legitimate interaction', () => {",
                "  repo.save(item);",
                "  expect(repo.save).toHaveBeenCalledWith(item);",
                "});",
            ]
        ),
    )
    _write(
        tmp_path / "tests" / "test_tautologies.py",
        "\n".join(
            [
                "def test_derived_expected():",
                "    actual = service.load()",
                "    expected_value = actual",
                "    assert actual == expected_value",
                "",
                "def test_mock_echo():",
                "    recorded = mock.call_args.args[0]",
                "    mock.assert_called_with(recorded)",
                "",
                "def test_legitimate_interaction():",
                "    repo.save.assert_called_with(item)",
            ]
        ),
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})
    weak = [
        finding for finding in result["findings"] if finding["rule_id"] == "weak-test-assertion"
    ]

    assert {finding["subtype"] for finding in weak} == {
        "literal",
        "self-comparison",
        "derived-expected",
        "mock-echo",
    }
    assert {
        finding["confidence"]
        for finding in weak
        if finding["subtype"] in {"literal", "self-comparison"}
    } == {"high"}
    assert {
        finding["severity"]
        for finding in weak
        if finding["subtype"] in {"derived-expected", "mock-echo"}
    } == {"observation"}
    assert not any(
        finding["file"] == "src/tautologies.test.ts"
        and "legitimate interaction" in finding["evidence"]
        for finding in weak
    )
    assert not any(
        finding["file"] == "tests/test_tautologies.py" and "repo.save" in finding["evidence"]
        for finding in weak
    )


def test_code_quality_reports_language_aware_complexity_metrics_and_hotspots(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "src" / "branchy.py",
        "\n".join(
            [
                "def branchy(value, other):",
                "    if value:",
                "        return 1",
                "    if other:",
                "        return 2",
                "    for item in values:",
                "        if item:",
                "            return item",
                "    return 0",
            ]
        ),
    )
    _write(
        tmp_path / "src" / "branchy.ts",
        "\n".join(
            [
                "export function branchy(value: boolean, other: boolean) {",
                "  if (value) return 1;",
                "  if (other) return 2;",
                "  for (const item of values) {",
                "    if (item) return item;",
                "  }",
                "  return 0;",
                "}",
            ]
        ),
    )

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={
            "structural_scan": {
                "complexity_thresholds": {"python": 3, "javascript": 2},
            }
        },
    )
    hotspots = [
        finding
        for finding in result["findings"]
        if finding["rule_id"] == "high-cyclomatic-complexity"
    ]

    assert result["summary"]["complexity_functions"] == 2
    assert result["summary"]["complexity_hotspots"] == 2
    assert {(item["language"], item["threshold"]) for item in result["complexity_metrics"]} == {
        ("python", 3),
        ("javascript", 2),
    }
    assert {(item["language"], item["value"]) for item in hotspots} == {
        ("python", 5),
        ("javascript", 5),
    }
    assert all("decision counts:" in item["evidence"] for item in hotspots)


def test_code_quality_can_disable_complexity_with_the_simplify_group(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "src" / "branchy.py",
        "def branchy(value):\n    if value:\n        return 1\n    if not value:\n        return 2\n    return 0\n",
    )

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "scan-001"},
        config={"structural_scan": {"disabled_rule_groups": ["simplify"]}},
    )

    assert result["complexity_metrics"] == []
    assert result["summary"]["complexity_functions"] == 0
    assert not any(
        finding["rule_id"] == "high-cyclomatic-complexity" for finding in result["findings"]
    )
