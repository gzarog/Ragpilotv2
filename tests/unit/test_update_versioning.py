"""``update/versioning.py``: MAJOR.MINOR.PATCH parsing/comparison, the
"v" prefix normalization git tags carry, and ``installed_version``'s tie
to ``ragpilot.__version__``.
"""

from __future__ import annotations

import pytest

from ragpilot import __version__
from ragpilot.update import versioning


def test_installed_version_matches_package_version() -> None:
    assert versioning.installed_version() == __version__


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("v0.1.8", "0.1.8"), ("V0.1.8", "0.1.8"), ("0.1.8", "0.1.8")],
)
def test_normalize_strips_leading_v(raw: str, expected: str) -> None:
    assert versioning.normalize(raw) == expected


@pytest.mark.parametrize("valid", ["0.1.8", "v0.1.8", "1.0.0", "10.20.30"])
def test_is_valid_accepts_plain_semver(valid: str) -> None:
    assert versioning.is_valid(valid)


@pytest.mark.parametrize(
    "invalid",
    ["ragpilot_0_1_0", "0.1", "0.1.8.1", "0.1.8-rc1", "", "not-a-version", "v0.1.8 "],
)
def test_is_valid_rejects_everything_else(invalid: str) -> None:
    assert not versioning.is_valid(invalid)


def test_parse_returns_int_tuple() -> None:
    assert versioning.parse("v1.2.3") == (1, 2, 3)


def test_parse_raises_value_error_on_invalid_input() -> None:
    with pytest.raises(ValueError, match="not a valid"):
        versioning.parse("ragpilot_0_1_0")


@pytest.mark.parametrize(
    ("candidate", "than", "expected"),
    [
        ("0.1.8", "0.1.7", True),
        ("0.2.0", "0.1.99", True),
        ("1.0.0", "0.99.99", True),
        ("0.1.7", "0.1.7", False),
        ("0.1.6", "0.1.7", False),
        ("v0.1.8", "0.1.7", True),  # normalizes both sides
    ],
)
def test_is_newer_compares_correctly(candidate: str, than: str, expected: bool) -> None:
    assert versioning.is_newer(candidate, than) is expected


def test_is_newer_never_trusts_an_invalid_candidate() -> None:
    # An untrusted tag straight from a GitHub API response must degrade
    # to "no update" rather than raise -- see this module's docstring.
    assert versioning.is_newer("ragpilot_0_1_0", "0.1.0") is False


def test_is_newer_never_trusts_an_invalid_baseline() -> None:
    assert versioning.is_newer("0.1.8", "not-a-version") is False
