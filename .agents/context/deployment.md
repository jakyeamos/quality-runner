# Deployment and rollback

last_reviewed: 2026-07-22

Normal development lands on the canonical `dev` branch. `main`, tags, PyPI,
Homebrew, and other publication surfaces are release-managed and require
explicit review.

Before release, run the documented test, static-analysis, build, installed-wheel
smoke, compatibility, and release-profile checks. Record artifact hashes and
the source revision. Do not publish from a dirty or unverifiable checkout.

Rollback is a forward, reviewed release to the last verified artifact or a
consumer pin to that artifact. Do not rewrite history or delete evidence.
Follow [docs/release.md](../../docs/release.md),
[docs/upgrade.md](../../docs/upgrade.md), and the
[release workflow](../../.github/workflows/release.yml).
