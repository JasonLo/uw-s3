"""Data models for sync mappings."""

import hashlib
from dataclasses import dataclass, field

from uw_s3 import CAMPUS_ENDPOINT


@dataclass
class SyncMap:
    """A mapping between a local directory and an S3 bucket/prefix."""

    local_dir: str
    bucket: str
    prefix: str = ""
    endpoint: str = CAMPUS_ENDPOINT
    id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.id:
            raw = f"{self.local_dir}:{self.bucket}:{self.prefix}:{self.endpoint}"
            self.id = hashlib.sha256(raw.encode()).hexdigest()[:12]
