"""Mount-health configuration and inspection for ``pi_stats``."""

from __future__ import annotations

import json
import os
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, NotRequired, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

MOUNTINFO_PATH = Path("/proc/self/mountinfo")
MOUNTINFO_ESCAPE = re.compile(r"\\([0-7]{3})")
MOUNT_ID = re.compile(r"^[a-z][a-z0-9_]*$")
MOUNTINFO_MIN_LEFT_FIELDS = 6
MOUNTINFO_MIN_RIGHT_FIELDS = 3


@dataclass(frozen=True, slots=True)
class MountCheck:
    """One configured filesystem mount whose health should be reported."""

    identifier: str
    path: str
    source: str
    required_directories: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MountInfo:
    """Relevant fields from one Linux mountinfo record."""

    path: str
    source: str
    mount_options: frozenset[str]
    super_options: frozenset[str]


class MountHealth(TypedDict):
    """Structured health state published for one configured mount."""

    healthy: bool
    path: str
    expected_source: str
    actual_source: NotRequired[str]
    mounted: bool
    source_matches: bool
    read_write: bool
    required_directories_present: dict[str, bool]
    missing_directories: list[str]
    reasons: list[str]


def _normalize_mount_path(path: str) -> str:
    """Normalize a Linux mountpoint path for mountinfo lookup."""
    normalized_path = posixpath.normpath(path)
    if normalized_path.startswith("//"):
        return f"/{normalized_path.lstrip('/')}"
    return normalized_path


def _sources_match(
    actual_source: str,
    expected_source: str,
    *,
    realpath: Callable[[str], str],
) -> bool:
    """Compare local sources by resolved path and other sources literally."""
    if (
        PurePosixPath(actual_source).root == "/"
        and PurePosixPath(expected_source).root == "/"
    ):
        return realpath(actual_source) == realpath(expected_source)
    return actual_source == expected_source


def _parse_required_directories(
    identifier: str,
    value: object,
) -> tuple[str, ...]:
    """Validate required directories for one mount check."""
    if not isinstance(value, list) or not all(
        isinstance(directory, str) for directory in value
    ):
        raise TypeError(
            f"Mount check {identifier!r} required_directories must be a list of strings",
        )

    directories: list[str] = []
    for directory in value:
        relative = PurePosixPath(directory)
        if (
            not directory
            or relative.is_absolute()
            or directory in {".", ".."}
            or ".." in relative.parts
        ):
            raise ValueError(
                f"Invalid required directory {directory!r} for {identifier!r}",
            )
        directories.append(directory)
    return tuple(directories)


def _parse_mount_check(index: int, item: object) -> MountCheck:
    """Validate one decoded mount check."""
    if not isinstance(item, dict):
        raise TypeError(f"Mount check {index} must be a JSON object")

    identifier = item.get("id")
    path = item.get("path")
    source = item.get("source")
    if not isinstance(identifier, str) or not MOUNT_ID.fullmatch(identifier):
        raise ValueError(
            f"Mount check {index} id must match {MOUNT_ID.pattern!r}",
        )
    if not isinstance(path, str):
        raise TypeError(f"Mount check {identifier!r} path must be a string")
    path = _normalize_mount_path(path)
    if not PurePosixPath(path).is_absolute():
        raise ValueError(f"Mount check {identifier!r} path must be absolute")
    if not isinstance(source, str):
        raise TypeError(f"Mount check {identifier!r} source must be a string")
    if not source:
        raise ValueError(f"Mount check {identifier!r} source must not be empty")

    return MountCheck(
        identifier=identifier,
        path=path,
        source=source,
        required_directories=_parse_required_directories(
            identifier,
            item.get("required_directories", []),
        ),
    )


def parse_mount_checks(raw: str) -> tuple[MountCheck, ...]:
    """Parse and validate ``PI_STATS_MOUNTS_JSON``."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("PI_STATS_MOUNTS_JSON must be valid JSON") from exc

    if not isinstance(value, list):
        raise TypeError("PI_STATS_MOUNTS_JSON must be a JSON list")

    checks: list[MountCheck] = []
    identifiers: set[str] = set()
    paths: set[str] = set()
    for index, item in enumerate(value):
        check = _parse_mount_check(index, item)
        if check.identifier in identifiers:
            raise ValueError(f"Duplicate mount check id: {check.identifier!r}")
        if check.path in paths:
            raise ValueError(f"Duplicate mount check path: {check.path!r}")

        identifiers.add(check.identifier)
        paths.add(check.path)
        checks.append(check)

    return tuple(checks)


def _unescape_mountinfo(value: str) -> str:
    """Decode the octal escapes used by procfs mountinfo."""
    return MOUNTINFO_ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), value)


def parse_mountinfo(text: str) -> dict[str, MountInfo]:
    """Parse mountinfo records keyed by exact mountpoint path."""
    mounts: dict[str, MountInfo] = {}
    for line in text.splitlines():
        left, separator, right = line.partition(" - ")
        if not separator:
            continue
        left_fields = left.split()
        right_fields = right.split()
        if (
            len(left_fields) < MOUNTINFO_MIN_LEFT_FIELDS
            or len(right_fields) < MOUNTINFO_MIN_RIGHT_FIELDS
        ):
            continue
        path = _unescape_mountinfo(left_fields[4])
        mounts[path] = MountInfo(
            path=path,
            source=_unescape_mountinfo(right_fields[1]),
            mount_options=frozenset(left_fields[5].split(",")),
            super_options=frozenset(right_fields[2].split(",")),
        )
    return mounts


def inspect_mount(
    check: MountCheck,
    mounts: Mapping[str, MountInfo],
    *,
    is_directory: Callable[[Path], bool] = Path.is_dir,
    realpath: Callable[[str], str] = os.path.realpath,
) -> MountHealth:
    """Evaluate one configured mount against a parsed mount table."""
    mount = mounts.get(check.path)
    mounted = mount is not None
    source_matches = bool(
        mount is not None
        and _sources_match(
            mount.source,
            check.source,
            realpath=realpath,
        ),
    )
    read_write = bool(
        mount is not None and "rw" in mount.mount_options and "rw" in mount.super_options,
    )
    required_directories_present = {
        directory: is_directory(Path(check.path) / directory)
        for directory in check.required_directories
    }
    missing_directories = [
        directory
        for directory, present in required_directories_present.items()
        if not present
    ]

    reasons: list[str] = []
    if not mounted:
        reasons.append("not_mounted")
    elif not source_matches:
        reasons.append("wrong_source")
    if mounted and not read_write:
        reasons.append("read_only")
    if missing_directories:
        reasons.append("missing_required_directories")

    health: MountHealth = {
        "healthy": not reasons,
        "path": check.path,
        "expected_source": check.source,
        "mounted": mounted,
        "source_matches": source_matches,
        "read_write": read_write,
        "required_directories_present": required_directories_present,
        "missing_directories": missing_directories,
        "reasons": reasons,
    }
    if mount is not None:
        health["actual_source"] = mount.source
    return health


def collect_mount_health(
    checks: tuple[MountCheck, ...],
    *,
    mountinfo_path: Path = MOUNTINFO_PATH,
) -> dict[str, MountHealth]:
    """Collect health for every configured mount without aborting other stats."""
    try:
        mounts = parse_mountinfo(mountinfo_path.read_text(encoding="utf-8"))
    except OSError:
        health_by_id = {check.identifier: inspect_mount(check, {}) for check in checks}
        for health in health_by_id.values():
            health["reasons"] = ["inspection_error"]
        return health_by_id
    return {check.identifier: inspect_mount(check, mounts) for check in checks}
