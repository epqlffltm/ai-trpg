# asset-server/app/images/setup.py

"""
설정으로 그림 저장소와 그림을 여는 것을 만든다(#566). 앱을 만들 때 한 번 부른다(app/main.py).
"""

import httpx

from app.core.config import Settings
from app.images.isolation import DecodeLimits, IsolatedDecoder
from app.images.sigv4 import Credentials
from app.images.store import ImageStore, S3ImageStore, StoreLocation, UnconfiguredImageStore

MEGABYTE = 1024 * 1024


def build_image_store(settings: Settings, client: httpx.AsyncClient) -> ImageStore:
    """설정의 저장소. 주소가 비었으면 늘 503 인 저장소다."""
    if not settings.image_store_endpoint:
        return UnconfiguredImageStore()
    credentials = Credentials(
        access_key_id=settings.image_store_access_key_id,
        secret_access_key=settings.image_store_secret_access_key.get_secret_value(),
        region=settings.image_store_region,
    )
    location = StoreLocation(origin=settings.image_store_endpoint.rstrip('/'), bucket=settings.image_store_bucket)
    return S3ImageStore(client, credentials, location, settings.image_store_timeout_seconds)


def build_decoder(settings: Settings) -> IsolatedDecoder:
    """설정의 상한으로 그림을 여는 것."""
    limits = DecodeLimits(
        max_pixels=settings.image_max_pixels,
        memory_bytes=settings.image_decode_memory_mb * MEGABYTE,
        cpu_seconds=settings.image_decode_cpu_seconds,
        wall_seconds=settings.image_decode_wall_seconds,
    )
    return IsolatedDecoder(limits, settings.image_decode_concurrency)
