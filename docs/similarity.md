# Similarity scanning

Quality Runner owns the default semantic similarity path. It is a standard-library Python scanner that extracts named JavaScript/TypeScript, Python, and Rust functions, normalizes comments/literals/local identifiers, and compares token shapes. It does not require Cargo, Tree-sitter, OXC, or a separately installed similarity binary.

The report uses the stable `quality-runner-similarity-v0.1` contract with an explicit `backend`, `status`, `clusters`, `findings`, and `scanner_status` field set. The native backend is selected by default:

```toml
[quality_runner.structural_scan]
similarity_backend = "native"
similarity_threshold = 0.87
similarity_min_lines = 8
similarity_max_pairs = 25
similarity_include_tests = false
```

The upstream-compatible scanners remain available as an opt-in compatibility backend. They are never installed or invoked by the native default:

```toml
[quality_runner.structural_scan]
similarity_backend = "external"
```

External mode looks for `similarity-ts`, `similarity-py`, and `similarity-rs` only when the repository contains the corresponding language. Missing tools are reported as scanner status; they do not fail the scan. This keeps the upstream project useful for comparison or higher-fidelity follow-up without making it a runtime dependency.

The design was informed by [mizchi/similarity](https://github.com/mizchi/similarity), an MIT-licensed Rust workspace with language-specific scanners. The QR-native implementation is independently owned; no upstream source is vendored into this repository. If upstream code is copied in a future change, retain its MIT notice and attribution.
