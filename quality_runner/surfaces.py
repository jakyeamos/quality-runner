from __future__ import annotations

import re
from pathlib import Path

from quality_runner.scan_exclusions import (
    iter_allowed_paths,
    resolve_scan_exclusions,
)

QUALITY_TARGETS = {
    "format": "formatter",
    "fmt": "formatter",
    "lint": "lint",
    "test": "tests",
    "tests": "tests",
    "build": "build",
    "smoke": "runtime_smoke",
    "smoke-test": "runtime_smoke",
}


def detect_surfaces(
    root: Path,
    scan_exclusions: list[str] | None = None,
) -> tuple[list[dict[str, str]], list[str], list[dict[str, str]]]:
    resolved_exclusions = resolve_scan_exclusions(
        {"scan_exclusions": scan_exclusions} if scan_exclusions is not None else None
    )
    surfaces: list[dict[str, str]] = []
    commands: list[dict[str, str]] = []
    generated_code: list[dict[str, str]] = []

    _detect_make(root, surfaces, commands)
    _detect_docker(root, surfaces, commands)
    _detect_terraform(root, surfaces, commands, resolved_exclusions)
    _detect_db_migrations(root, surfaces)
    _detect_contracts(root, surfaces, resolved_exclusions)
    _detect_generated(root, surfaces, generated_code, resolved_exclusions)
    _detect_monorepo(root, surfaces)

    ecosystems = sorted({surface["ecosystem"] for surface in surfaces})
    return surfaces, ecosystems, generated_code


def quality_commands_from_surfaces(
    root: Path,
    scan_exclusions: list[str] | None = None,
) -> list[dict[str, str]]:
    resolved_exclusions = resolve_scan_exclusions(
        {"scan_exclusions": scan_exclusions} if scan_exclusions is not None else None
    )
    surfaces: list[dict[str, str]] = []
    commands: list[dict[str, str]] = []
    _detect_make(root, surfaces, commands)
    _detect_docker(root, surfaces, commands)
    _detect_terraform(root, surfaces, commands, resolved_exclusions)
    return commands


def _detect_make(
    root: Path,
    surfaces: list[dict[str, str]],
    commands: list[dict[str, str]],
) -> None:
    makefile = root / "Makefile"
    if not makefile.is_file() or makefile.is_symlink():
        return
    text = _read_text(makefile)
    targets = sorted(
        {
            match.group(1)
            for match in re.finditer(r"^([A-Za-z0-9_.-]+):(?:\s|$)", text, re.MULTILINE)
            if not match.group(1).startswith(".")
        }
    )
    if not targets:
        return
    surfaces.append(
        {
            "id": "makefile",
            "kind": "task_runner",
            "ecosystem": "make",
            "path": "Makefile",
            "evidence": ",".join(targets),
        }
    )
    for target in targets:
        capability_id = QUALITY_TARGETS.get(target)
        if capability_id is None:
            continue
        commands.append(
            _quality_command(
                capability_id=capability_id,
                command=f"make {target}",
                source_type="make_target",
                source=f"Makefile:{target}",
                language="make",
            )
        )


def _detect_docker(
    root: Path,
    surfaces: list[dict[str, str]],
    commands: list[dict[str, str]],
) -> None:
    dockerfile = root / "Dockerfile"
    if dockerfile.is_file() and not dockerfile.is_symlink():
        surfaces.append(
            {
                "id": "dockerfile",
                "kind": "runtime",
                "ecosystem": "docker",
                "path": "Dockerfile",
                "evidence": "Dockerfile",
            }
        )
        commands.append(
            _quality_command(
                capability_id="build",
                command="docker build .",
                source_type="docker",
                source="Dockerfile",
                language="docker",
            )
        )

    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        path = root / name
        if path.is_file() and not path.is_symlink():
            surfaces.append(
                {
                    "id": "docker_compose",
                    "kind": "runtime",
                    "ecosystem": "docker",
                    "path": name,
                    "evidence": "compose file",
                }
            )
            commands.append(
                _quality_command(
                    capability_id="runtime_smoke",
                    command=f"docker compose -f {name} config",
                    source_type="docker",
                    source=name,
                    language="docker",
                )
            )
            break


def _detect_terraform(
    root: Path,
    surfaces: list[dict[str, str]],
    commands: list[dict[str, str]],
    scan_exclusions: list[str],
) -> None:
    terraform_dirs = sorted(
        {
            path.parent
            for path in iter_allowed_paths(root, scan_exclusions)
            if path.is_file() and path.suffix == ".tf"
        }
    )
    if not terraform_dirs:
        return
    first_dir = _relative(root, terraform_dirs[0])
    surfaces.append(
        {
            "id": "terraform",
            "kind": "infrastructure",
            "ecosystem": "terraform",
            "path": first_dir,
            "evidence": "*.tf",
        }
    )
    commands.extend(
        [
            _quality_command(
                capability_id="formatter",
                command="terraform fmt -check",
                source_type="terraform",
                source=first_dir,
                language="terraform",
            ),
            _quality_command(
                capability_id="lint",
                command="terraform validate",
                source_type="terraform",
                source=first_dir,
                language="terraform",
            ),
        ]
    )


def _detect_db_migrations(root: Path, surfaces: list[dict[str, str]]) -> None:
    candidates = ["alembic/versions", "migrations", "db/migrations", "prisma/migrations"]
    for candidate in candidates:
        path = root / candidate
        if path.is_dir() and not path.is_symlink():
            surfaces.append(
                {
                    "id": "db_migrations",
                    "kind": "database",
                    "ecosystem": "database",
                    "path": candidate,
                    "evidence": "migration directory",
                }
            )
            return


def _detect_contracts(
    root: Path,
    surfaces: list[dict[str, str]],
    scan_exclusions: list[str],
) -> None:
    for name in ("openapi.yaml", "openapi.yml", "openapi.json"):
        path = root / name
        if path.is_file() and not path.is_symlink():
            surfaces.append(
                {
                    "id": "openapi_contract",
                    "kind": "service_contract",
                    "ecosystem": "contract",
                    "path": name,
                    "evidence": "OpenAPI contract",
                }
            )
            break

    proto_files = sorted(
        path
        for path in iter_allowed_paths(root, scan_exclusions)
        if path.is_file() and path.suffix == ".proto"
    )
    if proto_files:
        surfaces.append(
            {
                "id": "protobuf_contract",
                "kind": "service_contract",
                "ecosystem": "contract",
                "path": _relative(root, proto_files[0]),
                "evidence": "*.proto",
            }
        )


def _detect_generated(
    root: Path,
    surfaces: list[dict[str, str]],
    generated_code: list[dict[str, str]],
    scan_exclusions: list[str],
) -> None:
    generated_dirs = sorted(
        path
        for path in iter_allowed_paths(root, scan_exclusions)
        if path.is_dir() and path.name in {"generated", "__generated__", "gen"}
    )
    if not generated_dirs:
        return
    rel_path = _relative(root, generated_dirs[0])
    generated_code.append({"path": rel_path, "evidence": "generated directory"})
    surfaces.append(
        {
            "id": "generated_code",
            "kind": "generated_code",
            "ecosystem": "generated",
            "path": rel_path,
            "evidence": "generated directory",
        }
    )


def _detect_monorepo(root: Path, surfaces: list[dict[str, str]]) -> None:
    monorepo_files = [
        ("turbo.json", "turborepo"),
        ("nx.json", "nx"),
        ("pnpm-workspace.yaml", "pnpm_workspace"),
    ]
    for filename, surface_id in monorepo_files:
        path = root / filename
        if path.is_file() and not path.is_symlink():
            surfaces.append(
                {
                    "id": surface_id,
                    "kind": "monorepo",
                    "ecosystem": "monorepo",
                    "path": filename,
                    "evidence": filename,
                }
            )


def _quality_command(
    *,
    capability_id: str,
    command: str,
    source_type: str,
    source: str,
    language: str,
) -> dict[str, str]:
    return {
        "id": capability_id,
        "command": command,
        "source_type": source_type,
        "source": source,
        "language": language,
    }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()
