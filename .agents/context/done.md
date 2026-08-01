# Definition of done

A Quality Runner change is complete only when:

- the affected CLI, MCP, workflow, artifact, schema, and documentation
  surfaces agree;
- behavior-focused tests cover the changed public contract or confirmed
  regression;
- locked pytest, Ruff lint, Ruff format, certified BasedPyright, Vulture,
  dependency audit, package build, and the environment contract pass;
- repository-wide strict BasedPyright is claimed only after its findings are
  remediated and the expanded scope has repeatable local and CI evidence;
- safety boundaries still refuse unauthorized source mutation, remote calls,
  credential collection, and remediation execution;
- generated evidence contains provenance and redaction metadata and no private
  values entered the public diff;
- the change is one coherent concern, reviewed, committed, and pushed to an
  explicitly selected branch.

A passing local gate does not prove the quality of a target repository,
benchmark validity, provider behavior, or PyPI publication. Those claims need
separate evidence.
