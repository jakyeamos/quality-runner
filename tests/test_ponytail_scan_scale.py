from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from quality_runner.code_quality_ponytail import _single_implementation_abstractions


@pytest.mark.parametrize(
    ("implementation", "expected"),
    [
        ("class Adapter implements Gateway {}", True),
        ("class Adapter extends Gateway {}", True),
        ("class Adapter implements Other,\nGateway {}", True),
        ("class Adapter implements Gateway, Gateway {}", True),
        ("class A implements Gateway {}\nclass B implements Gateway {}", False),
        ("class Adapter implements GatewayExtra {}", False),
        ("class Adapter implements Gatewayé {}", False),
        ("class Adapter implements Gateway$ {}", True),
        ("class Adapter implements Other {}", False),
    ],
)
def test_implementation_index_preserves_name_boundaries(
    implementation: str, expected: bool
) -> None:
    source = f"interface Gateway {{}}\n{implementation}"
    findings = _single_implementation_abstractions(
        [{"path": "service.ts", "text": source, "lines": source.splitlines()}]
    )
    assert bool(findings) is expected
    if findings:
        assert findings[0]["rule_id"] == "single-implementation-abstraction"
        assert findings[0]["file"] == "service.ts"


def test_large_scan_does_not_rescan_the_corpus_for_every_declaration() -> None:
    # Real detector in a bounded subprocess: a corpus-wide regex per declaration
    # exceeds this generous budget; one inheritance index completes promptly.
    script = """
from quality_runner.code_quality_ponytail import _single_implementation_abstractions
declarations = '\\n'.join(f'interface Contract{i} {{}}' for i in range(1000))
implementations = '\\n'.join(f'class C{i} implements Contract{i} {{}}' for i in range(1000))
padding = '// ' + ('ordinary source text ' * 100000)
findings = _single_implementation_abstractions([
    {'path': 'contracts.ts', 'text': declarations, 'lines': declarations.splitlines()},
    {'path': 'implementations.ts', 'text': implementations},
    {'path': 'padding.ts', 'text': padding},
])
assert len(findings) == 1000
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stderr
