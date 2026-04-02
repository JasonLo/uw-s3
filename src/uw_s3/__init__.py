import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from minio import Minio
from minio.commonconfig import CopySource
from minio.deleteobjects import DeleteObject

__version__ = "0.4.0"


@dataclass
class ObjectInfo:
    """Metadata for a single S3 object."""

    name: str
    size: int
    last_modified: datetime | None
    is_dir: bool = False


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
                is_dir=obj.is_dir,
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

    def bucket_exists(self, bucket: str) -> bool:
        """Check if a bucket exists."""
        return self.client.bucket_exists(bucket)

    def create_bucket(self, bucket: str) -> None:
        """Create a new bucket."""
        self.client.make_bucket(bucket)

    def empty_bucket(self, bucket: str) -> None:
        """Delete all objects in a bucket."""
        objects = list(self.client.list_objects(bucket, recursive=True))
        if objects:
            errors = list(
                self.client.remove_objects(
                    bucket, [DeleteObject(obj.object_name) for obj in objects]
                )
            )
            if errors:
                raise RuntimeError(f"Failed to delete objects: {errors[0].message}")

    def set_bucket_policy(self, bucket: str, permission: str) -> None:
        """Set bucket access policy: 'private', 'public-read', or 'public-readwrite'."""
        valid = {"private", "public-read", "public-readwrite"}
        if permission not in valid:
            raise ValueError(
                f"Unknown permission {permission!r}, must be one of {valid}"
            )
        if permission == "private":
            self.client.delete_bucket_policy(bucket)
            return
        statements: list[dict] = [
            {
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
                "Resource": f"arn:aws:s3:::{bucket}",
            },
        ]
        if permission == "public-read":
            statements.append(
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                }
            )
        elif permission == "public-readwrite":
            statements.append(
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": [
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject",
                    ],
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                }
            )
        policy = {"Version": "2012-10-17", "Statement": statements}
        self.client.set_bucket_policy(bucket, json.dumps(policy))

    def delete_object(self, bucket: str, object_name: str) -> None:
        """Delete a single object from a bucket."""
        self.client.remove_object(bucket, object_name)

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        """Delete all objects under a prefix. Returns count of deleted objects."""
        objects = list(self.client.list_objects(bucket, prefix=prefix, recursive=True))
        if not objects:
            return 0
        errors = list(
            self.client.remove_objects(
                bucket, [DeleteObject(obj.object_name) for obj in objects]
            )
        )
        if errors:
            raise RuntimeError(f"Failed to delete objects: {errors[0].message}")
        return len(objects)

    def copy_object(self, bucket: str, src_key: str, dst_key: str) -> None:
        """Copy a single object to a new key within the same bucket."""
        self.client.copy_object(bucket, dst_key, CopySource(bucket, src_key))

    def copy_prefix(self, bucket: str, src_prefix: str, dst_prefix: str) -> int:
        """Copy all objects under src_prefix to dst_prefix. Returns count."""
        objects = list(self.client.list_objects(bucket, prefix=src_prefix, recursive=True))
        for obj in objects:
            new_key = dst_prefix + obj.object_name[len(src_prefix):]
            self.client.copy_object(bucket, new_key, CopySource(bucket, obj.object_name))
        return len(objects)

    def rename_object(self, bucket: str, old_key: str, new_key: str) -> None:
        """Rename a single object (copy + delete)."""
        self.copy_object(bucket, old_key, new_key)
        self.delete_object(bucket, old_key)

    def rename_prefix(self, bucket: str, old_prefix: str, new_prefix: str) -> int:
        """Rename/move a folder prefix (copy all + delete all). Returns count."""
        count = self.copy_prefix(bucket, old_prefix, new_prefix)
        self.delete_prefix(bucket, old_prefix)
        return count

    def delete_bucket(self, bucket: str) -> None:
        """Remove an empty bucket."""
        self.client.remove_bucket(bucket)
