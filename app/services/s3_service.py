"""
S3 service — study material PDFs.

Objects are stored under a class/subject/chapter path and referenced in
sgs_file_storage_metadata.file_url as an ``s3://bucket/key`` URI (never a
browsable https URL — the bucket is private). Reads go through a short-lived
presigned URL generated on demand.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from saraswati_tenant import build_key as kit_build_key
from saraswati_tenant import current_school, s3_path_validator

from app.core.config import settings

PREFIX = "study-material"
ASSIGNMENT_PREFIX = "assignments"
PRESIGN_EXPIRY = 3600  # 1 hour


def _client():
    # ap-south-2 is an opt-in region: the endpoint must be regional, otherwise
    # presigned URLs point at the global host and S3 rejects them with
    # IllegalLocationConstraintException.
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        endpoint_url=f"https://s3.{settings.AWS_REGION}.amazonaws.com",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def _slugify(filename: str) -> str:
    """Keep the extension, make the stem URL-safe (matches existing key style)."""
    stem, _, ext = filename.rpartition(".")
    stem = stem or filename
    ext = f".{ext}" if ext and stem != filename else ""
    stem = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-")
    return f"{stem}{ext}"


def build_key(class_id, subject_id, chapter_id, filename: str) -> str:
    """{tenant}/study-material/class-18/subject-26/chapter-38/<ts>-<uuid8>-<slug>.pdf

    One bucket holds every school, so the school id is the first segment of the
    key and the only thing keeping two schools' files apart. The kit's builder
    puts it there; the path below it is unchanged, so existing readers still
    recognise the shape.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return kit_build_key(
        PREFIX,
        f"class-{class_id}",
        f"subject-{subject_id}",
        f"chapter-{chapter_id}",
        f"{ts}-{uuid.uuid4().hex[:8]}-{_slugify(filename)}",
    )


def build_assignment_key(class_id, assignment_id, filename: str) -> str:
    """{tenant}/assignments/class-18/assignment-42/<ts>-<uuid8>-<slug>.<ext>"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return kit_build_key(
        ASSIGNMENT_PREFIX,
        f"class-{class_id}",
        f"assignment-{assignment_id}",
        f"{ts}-{uuid.uuid4().hex[:8]}-{_slugify(filename)}",
    )


def to_uri(key: str) -> str:
    return f"s3://{settings.AWS_S3_BUCKET_NAME}/{key}"


def parse_uri(file_url: str) -> tuple[str, str]:
    """s3://bucket/key -> (bucket, key). Also tolerates a plain https URL."""
    if file_url.startswith("s3://"):
        p = urlparse(file_url)
        return p.netloc, p.path.lstrip("/")
    p = urlparse(file_url)
    if p.netloc.endswith("amazonaws.com"):
        return p.netloc.split(".")[0], p.path.lstrip("/")
    return settings.AWS_S3_BUCKET_NAME, file_url.lstrip("/")


def upload_file(body: bytes, key: str, content_type: str = "application/octet-stream") -> str:
    """Put the object (any file type) and return its s3:// URI."""
    if not settings.AWS_S3_BUCKET_NAME:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "S3 is not configured")
    try:
        _client().put_object(
            Bucket=settings.AWS_S3_BUCKET_NAME,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
    except ClientError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Upload to S3 failed: {e}")
    return to_uri(key)


def presign_get(file_url: str) -> Optional[str]:
    """Temporary https URL so the browser can open a private object."""
    if not file_url:
        return None
    bucket, key = parse_uri(file_url)

    # The key came out of a row this request was allowed to read, but a row can
    # still hold a key written before the school prefix existed, or one copied
    # in by hand. Refusing anything that does not start with this school's id is
    # what stops a stale or crafted value handing out another school's file.
    s3_path_validator(key, current_school().tenant_id)

    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=PRESIGN_EXPIRY,
        )
    except ClientError:
        return None


def delete_object(file_url: str) -> bool:
    """Hard-delete from S3 — only used by the year-end purge, not by replace/delete."""
    bucket, key = parse_uri(file_url)
    try:
        _client().delete_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False
