from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

from minio import Minio
from minio.error import S3Error


@dataclass
class ObjectInfo:
    """Metadata for a single S3 object."""

    name: str
    size: int
    last_modified: datetime | None


CAMPUS_ENDPOINT = "campus.s3.wisc.edu"
WEB_ENDPOINT = "web.s3.wisc.edu"


class UWS3:
    """Simple binding for UW-Madison Research Object Storage (S3)."""

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        *,
        endpoint: str = CAMPUS_ENDPOINT,
        secure: bool = True,
    ) -> None:
        self.endpoint = endpoint
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    @classmethod
    def campus(cls, access_key: str, secret_key: str) -> UWS3:
        """Connect via the campus-only pool (requires UW network/VPN)."""
        return cls(access_key, secret_key, endpoint=CAMPUS_ENDPOINT)

    @classmethod
    def web(cls, access_key: str, secret_key: str) -> UWS3:
        """Connect via the web pool (any network)."""
        return cls(access_key, secret_key, endpoint=WEB_ENDPOINT)

    @staticmethod
    def default_bucket(netid: str) -> str:
        """Return the default bucket name for a given NetID."""
        return f"{netid}-bucket-01"

    def list_buckets(self) -> list[str]:
        return [b.name for b in self.client.list_buckets()]

    def list_objects(
        self, bucket: str, *, prefix: str = "", recursive: bool = True
    ) -> list[str]:
        return [
            obj.object_name
            for obj in self.client.list_objects(
                bucket, prefix=prefix, recursive=recursive
            )
        ]

    def list_objects_with_size(
        self, bucket: str, *, prefix: str = "", recursive: bool = True
    ) -> list[tuple[str, int]]:
        """Return (object_name, size) pairs for objects in a bucket."""
        return [
            (obj.object_name, obj.size or 0)
            for obj in self.client.list_objects(
                bucket, prefix=prefix, recursive=recursive
            )
        ]

    def list_objects_detail(
        self, bucket: str, *, prefix: str = "", recursive: bool = True
    ) -> list[ObjectInfo]:
        """Return detailed metadata for objects in a bucket."""
        return [
            ObjectInfo(
                name=obj.object_name,
                size=obj.size or 0,
                last_modified=obj.last_modified,
            )
            for obj in self.client.list_objects(
                bucket, prefix=prefix, recursive=recursive
            )
        ]

    def upload_file(self, bucket: str, object_name: str, file_path: str | Path) -> None:
        self.client.fput_object(bucket, object_name, str(file_path))

    def download_file(
        self, bucket: str, object_name: str, file_path: str | Path
    ) -> None:
        self.client.fget_object(bucket, object_name, str(file_path))

    def put_bytes(self, bucket: str, object_name: str, data: bytes) -> None:
        self.client.put_object(bucket, object_name, BytesIO(data), len(data))

    def get_bytes(self, bucket: str, object_name: str) -> bytes:
        resp = self.client.get_object(bucket, object_name)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def delete(self, bucket: str, object_name: str) -> None:
        self.client.remove_object(bucket, object_name)

    def presigned_get(
        self, bucket: str, object_name: str, *, expires: timedelta = timedelta(hours=1)
    ) -> str:
        return self.client.presigned_get_object(bucket, object_name, expires=expires)

    def exists(self, bucket: str, object_name: str) -> bool:
        try:
            self.client.stat_object(bucket, object_name)
            return True
        except S3Error:
            return False

    def bucket_exists(self, bucket: str) -> bool:
        """Check if a bucket exists."""
        return self.client.bucket_exists(bucket)

    def create_bucket(self, bucket: str) -> None:
        """Create a new bucket."""
        self.client.make_bucket(bucket)

    def stat_object(self, bucket: str, object_name: str) -> object:
        """Return stat info for an object (size, last_modified, etc.)."""
        return self.client.stat_object(bucket, object_name)
