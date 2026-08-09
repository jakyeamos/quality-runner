# Skill capability evidence

Quality Runner keeps domain skills unchanged. During a code-quality scan it derives a
`skill_capabilities` projection that answers four separate questions:

- Should this representation produce findings?
- Which finding classes are actually represented?
- Which backfill phases are available (`detect`, `report`, `plan`, `apply`, `verify`)?
- Is the representation only configured, covered by a scan, or still unreviewed?

The projection is report-only. `apply` is intentionally unsupported in the capability
record; remediation remains owner-controlled and requires a later verification gate.

To publish the projection for Pronto's Skills tab after a scan:

```bash
qr skill capabilities path/to/code-quality-scan.json --write
```

The default output is:

```text
~/.quality-runner/skill-capabilities/current/capabilities.json
```

Use `--output PATH` for a preview or an explicitly scoped artifact. Without `--write`,
the command only emits the derived payload.

Quality Runner records representation status as `adapter_defined`, `configured`,
`scan_observed`, `coverage_proven`, or `unknown`. A persisted capability feed is
evidence of the projection that produced it; it is not, by itself, proof of a fresh
dynamic run or a passed remediation/verification gate.

The native `debloat` category is included even when no active Quality Runner skill pack
is configured. Its size and router findings are structural triggers for a read-only
ownership review; they are not proof of bloat or authorization to delete code.
