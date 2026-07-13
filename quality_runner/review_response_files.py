from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path

from quality_runner.artifacts import safe_child_file


class ReviewAdapterResponseError(ValueError):
    """The submitted adapter response cannot be used as local review evidence."""


class ReviewAdapterResponsePermissionError(ReviewAdapterResponseError):
    """The submitted response path is outside the permitted review directory."""


def read_local_adapter_response(
    *,
    allowed_directory: Path,
    response_path: Path,
    relative_root: Path,
    maximum_bytes: int,
) -> dict[str, object]:
    """Read one bounded direct JSON response from an approved local directory."""
    directory = allowed_directory.expanduser().absolute()
    candidate = response_path.expanduser()
    if not candidate.is_absolute():
        candidate = relative_root.expanduser().resolve() / candidate
    candidate = candidate.absolute()
    if candidate.parent != directory:
        raise ReviewAdapterResponsePermissionError(
            "adapter output must be a direct file inside the approved review directory"
        )
    try:
        path = safe_child_file(directory, candidate.name, require_exists=True)
    except (FileNotFoundError, ValueError) as error:
        raise ReviewAdapterResponsePermissionError(
            f"adapter output cannot be safely read: {error}"
        ) from error
    try:
        payload = json.loads(read_regular_text_file(path, maximum_bytes=maximum_bytes))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ReviewAdapterResponseError(f"adapter output is not readable JSON: {error}") from error
    if not isinstance(payload, Mapping):
        raise ReviewAdapterResponseError("adapter output must be a JSON object")
    return dict(payload)


def read_regular_text_file(path: Path, *, maximum_bytes: int) -> str:
    """Read a direct regular UTF-8 file without following its final path component."""
    directory_descriptor = open_checked_directory(path.parent)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path.name,
            os.O_RDONLY | nonblocking_flag() | no_follow_flag(),
            dir_fd=directory_descriptor,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("adapter output must be a regular file")
        if metadata.st_size > maximum_bytes:
            raise ValueError("adapter output exceeds the local size limit")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        if remaining == 0:
            raise ValueError("adapter output exceeds the local size limit")
        return b"".join(chunks).decode("utf-8")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_descriptor)


def open_checked_directory(path: Path) -> int:
    return os.open(path, os.O_RDONLY | directory_flag() | no_follow_flag())


def directory_flag() -> int:
    return getattr(os, "O_DIRECTORY", 0)


def no_follow_flag() -> int:
    return getattr(os, "O_NOFOLLOW", 0)


def nonblocking_flag() -> int:
    return getattr(os, "O_NONBLOCK", 0)
