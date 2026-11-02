# Definition of done

Last reviewed: 2026-11-02

A Quality Runner change is complete only when:

- the affected CLI, MCP, workflow, artifact, schema, and documentation
  surfaces agree;
- behavior-focused tests cover the changed public contract or confirmed
  regression;
- locked pytest, Ruff lint, Ruff format, standard and strict BasedPyright, Vulture,
  dependency audit, package build, and the environment contract pass;
- the pinned strict baseline remains at zero diagnostics, and current local
  results are distinguished from the exact revision covered by hosted CI;
- safety boundaries still refuse unauthorized source mutation, remote calls,
  credential collection, and remediation execution;
- generated evidence contains provenance and redaction metadata and no private
  values entered the public diff;
- the change is one coherent concern, reviewed, committed, and pushed to an
  explicitly selected branch.

A passing local gate does not prove the quality of a target repository,
benchmark validity, provider behavior, or PyPI publication. Those claims need
separate evidence.
