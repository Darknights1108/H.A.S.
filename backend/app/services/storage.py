"""MinIO object storage for resume files. Point the endpoint at real S3 in production."""

import io
import logging

from minio import Minio

from ..config import settings

logger = logging.getLogger(__name__)
_client: Minio | None = None

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}


def client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


def ensure_bucket() -> None:
    c = client()
    if not c.bucket_exists(settings.minio_bucket):
        c.make_bucket(settings.minio_bucket)
        logger.info("created bucket %s", settings.minio_bucket)


def put_resume(key: str, data: bytes, ext: str) -> None:
    ensure_bucket()
    client().put_object(
        settings.minio_bucket, key, io.BytesIO(data), len(data),
        content_type=CONTENT_TYPES.get(ext, "application/octet-stream"),
    )


def get_resume(key: str) -> bytes:
    resp = client().get_object(settings.minio_bucket, key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()
