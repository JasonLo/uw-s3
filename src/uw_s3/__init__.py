"""uw-s3 — Terminal UI for UW-Madison Research Object Storage."""

from importlib.metadata import version

from uw_s3.client import CAMPUS_ENDPOINT, WEB_ENDPOINT, ObjectInfo, UWS3

__version__ = version("uw-s3")

__all__ = ["CAMPUS_ENDPOINT", "WEB_ENDPOINT", "ObjectInfo", "UWS3", "__version__"]
