"""Tests for the updater module."""

import pytest

from uw_s3.updater import _is_newer, _parse_version


@pytest.mark.parametrize(
    "v,expected",
    [
        ("0.5.0", (0, 5, 0)),
        ("1.0", (1, 0)),
        ("10", (10,)),
        ("0.5.0rc1", None),
        ("v0.5.0", None),
        ("", None),
        ("1.0-beta", None),
    ],
)
def test_parse_version(v: str, expected: tuple[int, ...] | None) -> None:
    assert _parse_version(v) == expected


@pytest.mark.parametrize(
    "latest,current,expected",
    [
        ("0.5.1", "0.5.0", True),
        ("0.5.0", "0.5.0", False),
        ("0.5.0", "0.5.1", False),
        # Padding: "1.0" should equal "1.0.0", not be older.
        ("1.0", "1.0.0", False),
        ("1.0.0", "1.0", False),
        ("1.0.1", "1.0", True),
        # Major bump.
        ("1.0.0", "0.9.9", True),
        # Non-numeric tag — never offers an update.
        ("0.6.0rc1", "0.5.0", False),
        ("0.5.0", "0.5.0rc1", False),
    ],
)
def test_is_newer(latest: str, current: str, expected: bool) -> None:
    assert _is_newer(latest, current) is expected
