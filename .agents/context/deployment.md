# Packaging, deployment, and rollback

Last reviewed: 2026-08-02

Quality Runner is a Python package and CLI, not a hosted service. CI builds the
wheel and sdist, runs the locked quality ladder, smoke-tests installed console
scripts, and audits dependencies. Release workflow publication uses PyPI
trusted publishing from a reviewed `v*.*.*` tag on `main`; ordinary tests must
not publish or tag.

Before release, update version metadata, changelog, plugin manifests, citation
metadata, and compatibility fixtures as applicable. Build the package and
inspect it in a fresh virtual environment before publication.

Rollback before publication is a normal `git revert`. After publication,
select the prior known-good package version or release a corrective patch.
Never rewrite release history, delete compatibility fixtures, or lower a gate
to force a release through.
