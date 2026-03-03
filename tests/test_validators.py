"""Tests for shared validators."""

from uw_s3.validators import BUCKET_NAME_RE


def test_valid_bucket_names() -> None:
    valid = ["my-bucket-01", "abc", "a-b", "123", "a.b.c", "a" * 63]
    for name in valid:
        assert BUCKET_NAME_RE.match(name), f"{name!r} should be valid"


def test_invalid_bucket_names() -> None:
    invalid = [
        "",
        "ab",  # too short (min 3)
        "-abc",  # starts with hyphen
        "abc-",  # ends with hyphen
        "ABC",  # uppercase
        "a" * 64,  # too long
        "a b",  # space
    ]
    for name in invalid:
        assert not BUCKET_NAME_RE.match(name), f"{name!r} should be invalid"
