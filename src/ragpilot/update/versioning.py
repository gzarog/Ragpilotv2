"""Semantic-version parsing/comparison for the update subsystem.

Deliberately minimal: RAGpilot's own release process (this plan's Phase 6)
only ever produces plain ``MAJOR.MINOR.PATCH`` tags, so full SemVer 2.0
pre-release/build-metadata precedence rules are out of scope here -- a
version string carrying either is rejected as invalid rather than
half-handled.
"""

from __future__ import annotations

import re

from ragpilot import __version__

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def installed_version() -> str:
    return __version__


def normalize(version: str) -> str:
    """Strips a leading ``v``/``V`` -- git tags are ``v0.1.8``, but this
    codebase's own ``__version__`` and every comparison here work on the
    bare form. Callers should normalize any externally-sourced version
    (e.g. a GitHub release's ``tag_name``) before comparing or storing it.
    """
    return version[1:] if version[:1] in ("v", "V") else version


def is_valid(version: str) -> bool:
    return _SEMVER_RE.match(normalize(version)) is not None


def parse(version: str) -> tuple[int, int, int]:
    match = _SEMVER_RE.match(normalize(version))
    if match is None:
        raise ValueError(f"{version!r} is not a valid MAJOR.MINOR.PATCH version")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def is_newer(candidate: str, than: str) -> bool:
    """True when ``candidate`` is a strictly newer, valid version than
    ``than``. An invalid ``candidate`` -- e.g. straight from an untrusted
    GitHub API response -- is never considered newer rather than raising,
    so a malformed or unexpected tag degrades to "no update available"
    instead of crashing the check (see this plan's Security Requirements).
    """
    if not is_valid(candidate) or not is_valid(than):
        return False
    return parse(candidate) > parse(than)
