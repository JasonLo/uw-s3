"""Shared validation helpers."""

from __future__ import annotations

import re

BUCKET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$")
