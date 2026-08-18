# Developer legibility and change-surface maturity

Last reviewed: 2026-08-16.

`developer_legibility` measures whether a developer new to a repository can
orient, navigate, understand contracts and rationale, run the code, and make a
bounded change safely. It complements `change_surface_hotspots`, which detects
multi-signal areas where future changes are likely to amplify.

## Developer-legibility standard

Run the scoped audit with:

```bash
qr fleet audit run --repo-path /path/to/repository \
  --standard developer-legibility --json
```

The audit has eight lanes:

1. orientation: purpose, quick start, verification command, and repository map;
2. navigation and traceability: resolving documentation and source-line links;
3. architecture visibility: linked or embedded views where infrastructure makes them applicable;
4. semantic naming: domain-oriented public names, with vague-name findings and mandatory reviewer judgment;
5. public contracts: docstrings or doc comments for caller-visible behavior, errors, side effects, and invariants;
6. rationale and invariants: reasons for suppressions, debt markers, constraints, and non-obvious choices;
7. executable understanding: documented commands plus tests or examples;
8. ownership and freshness: bounded review evidence for maintained guidance.

The maturity scale is `0 unknown`, `1 ad hoc`, `2 defined`, `3 enforced`, and
`4 newcomer verified`. A missing quick start or less than 60% public-contract
coverage caps the result at level 2. Static evidence is capped at level 3.
Level 4 requires `.quality-runner/developer-legibility.json` with schema
`quality-runner-developer-legibility-evidence/v1`, the exact audited commit, and
passed evidence for `orient`, `run`, `locate_behavior`, `explain_invariant`, and
`bounded_change` tasks.

Naming conventions should make functions read as actions, types and values as
domain nouns, booleans as predicates, units explicit, and lifecycle state
transitions unambiguous. Avoid generic public names such as `data`, `helper`,
`manager`, `process`, and `util` unless the repository domain gives them a
specific, documented meaning.

Code should state what happens, names should carry meaning, comments should
explain why, and docstrings should define the caller contract. Comments that
merely restate syntax do not increase maturity. Suppressions and TODO/FIXME
markers need a reason, issue, or removal condition. The detector does not use
raw comment density as a score.

## Change-surface hotspots

The hotspot audit combines bounded Git co-change, local structural coupling,
and repeated-concept signals. A hotspot requires at least two independent
families. It is a review queue, not an automatic refactoring or tokenization
instruction; reviewers still decide ownership, compatibility, and the correct
shared seam.
