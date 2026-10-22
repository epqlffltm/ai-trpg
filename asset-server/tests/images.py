# asset-server/tests/images.py

"""
그림을 보는 테스트가 함께 쓰는 것. 가짜 저장소와 Pillow 로 만든 작은 그림들이다.

  - FakeImageStore: 넣은 객체를 메모리에 둔다. 서명한 주소는 저장소의 주소 모양을 흉내 낸다. 고장 낼 수 있다.
  - png_bytes, jpeg_bytes, webp_bytes: 크기와 색을 정한 그림. JPEG 에는 EXIF(방향, 설명)를 붙일 수 있다.
  - animated_webp: 장이 둘인 움직이는 WebP.
"""

import io
from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image

from app.images.store import ImageStoreUnavailableError

STORE_ORIGIN = 'http://object-store:8333'
STORE_BUCKET = 'ai-trpg-images'
# EXIF 의 방향(Orientation)과 설명(ImageDescription) 칸의 번호
ORIENTATION = 0x0112
DESCRIPTION = 0x010E


@dataclass(frozen=True)
class StoredObject:
    """가짜 저장소에 넣은 객체 하나."""

    data: bytes
    content_type: str


@dataclass
class FakeImageStore:
    """메모리에 두는 저장소. broken 이면 무엇을 하든 ImageStoreUnavailableError 다."""

    objects: dict[str, StoredObject] = field(default_factory=dict)
    broken: bool = False

    async def put(self, key: str, data: bytes, content_type: str, now: datetime) -> None:
        if self.broken:
            raise ImageStoreUnavailableError('고장')
        self.objects[key] = StoredObject(data, content_type)

    def presigned_get(self, key: str, now: datetime) -> str:
        if self.broken:
            raise ImageStoreUnavailableError('고장')
        return f'{STORE_ORIGIN}/{STORE_BUCKET}/{key}?X-Amz-Expires=60&X-Amz-Signature=fake'


def solid(size: tuple[int, int], color: tuple[int, ...], mode: str = 'RGB') -> Image.Image:
    """한 가지 색으로 칠한 그림."""
    return Image.new(mode, size, color)


def encoded(image: Image.Image, image_format: str, **options) -> bytes:
    """그 형식으로 인코딩한 바이트."""
    output = io.BytesIO()
    image.save(output, format=image_format, **options)
    return output.getvalue()


def png_bytes(size: tuple[int, int] = (4, 3), color: tuple[int, ...] = (200, 10, 10)) -> bytes:
    """작은 PNG."""
    return encoded(solid(size, color), 'PNG')


def webp_bytes(size: tuple[int, int] = (4, 3)) -> bytes:
    """작은 WebP. 투명이 있다."""
    return encoded(solid(size, (10, 200, 10, 128), mode='RGBA'), 'WEBP')


def jpeg_bytes(size: tuple[int, int] = (4, 2), orientation: int | None = None, description: str | None = None) -> bytes:
    """작은 JPEG. 방향과 설명을 EXIF 로 붙일 수 있다."""
    exif = Image.Exif()
    if orientation is not None:
        exif[ORIENTATION] = orientation
    if description is not None:
        exif[DESCRIPTION] = description
    return encoded(solid(size, (10, 10, 200)), 'JPEG', exif=exif.tobytes())


def animated_webp(size: tuple[int, int] = (4, 3)) -> bytes:
    """장이 둘인 WebP. 첫 장은 빨강, 둘째 장은 파랑이다."""
    frames = [solid(size, (255, 0, 0)), solid(size, (0, 0, 255))]
    return encoded(frames[0], 'WEBP', save_all=True, append_images=frames[1:], duration=100, lossless=True)


def opened(data: bytes) -> Image.Image:
    """바이트를 연 그림."""
    image = Image.open(io.BytesIO(data))
    image.load()
    return image
