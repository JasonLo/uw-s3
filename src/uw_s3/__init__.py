"""uw-s3 — Terminal UI for UW-Madison Research Object Storage."""

from uw_s3.client import CAMPUS_ENDPOINT, WEB_ENDPOINT, ObjectInfo, UWS3

__version__ = "0.5.0"

__all__ = ["CAMPUS_ENDPOINT", "WEB_ENDPOINT", "ObjectInfo", "UWS3", "__version__"]
