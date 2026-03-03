"""Data models for sync mappings."""

from dataclasses import dataclass, field


@dataclass
class SyncMap:
    """A mapping between a local directory and an S3 bucket/prefix."""

    local_dir: str
    bucket: str
    prefix: str = ""
    endpoint: str = "campus.s3.wisc.edu"
    id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.id:
            import hashlib

            raw = f"{self.local_dir}:{self.bucket}:{self.prefix}:{self.endpoint}"
            self.id = hashlib.sha256(raw.encode()).hexdigest()[:12]
