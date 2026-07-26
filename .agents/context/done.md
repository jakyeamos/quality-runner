# Definition of done

A Quality Runner change is complete only when:

- the affected CLI, MCP, workflow, artifact, schema, and documentation
  surfaces agree;
- behavior-focused tests cover the changed public contract or confirmed
  regression;
- locked pytest, Ruff lint, Ruff format, BasedPyright, Vulture, dependency
  audit, package build, and the environment contract pass;
- safety boundaries still refuse unauthorized source mutation, remote calls,
  credential collection, and remediation execution;
- generated evidence contains provenance and redaction metadata and no private
  values entered the public diff;
- the change is one coherent concern, reviewed, committed, and pushed to an
  explicitly selected branch.

A passing local gate does not prove the quality of a target repository,
benchmark validity, provider behavior, or PyPI publication. Those claims need
separate evidence.
