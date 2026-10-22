# asset-server/app/images/service.py

"""
그림을 올리고 내준다(#566, docs/architecture/asset-server.md 의 "그림").

올리기: 형식을 머리로 고른다 → 따로 된 프로세스에서 열어 다시 인코딩한다 → 저장소에 넣는다 → 행을 적는다.
  - DB 연결은 맨 끝(행을 적을 때)에만 잡는다. 여는 일과 저장소에 넣는 일은 몇 초가 걸릴 수 있다.
  - 저장소에 넣은 뒤 행을 적지 못하면 저장소에 주인 없는 객체가 남는다. 아무도 가리키지 않아 내주지 않는다.
    반대 차례(행 먼저)면 바이트가 없는 그림을 가리키는 행이 남는다. 앞쪽이 덜 해롭다.
내주기: 볼 수 있으면 본문 없이 X-Accel-Redirect 와 X-Image-Source(저장소의 서명한 주소)를 답한다. nginx 가 받아 내준다.
  - 지금은 주인만 본다. 볼 수 없으면 없는 그림과 같다(404). 공개 캐릭터의 그림을 남이 보는 규칙은 다음 PR 이다.

HTTP 를 모른다. 예외로 알리고 라우터가 응답으로 바꾼다.
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.images import repository
from app.images.formats import CONTENT_TYPES, ImageFormat, check_image_header
from app.images.isolation import DecodedImage, ImageDecoder
from app.images.models import Image
from app.images.store import ImageStore

# 그림을 내주는 주소. 소개 글의 img 가 이 모양만 받는다(app/content/html.py 의 IMAGE)
IMAGES_PATH = '/api/v1/asset/images'
# nginx 의 내부 위치(docker/nginx/templates/api.inc.template 의 /_images/)
ACCEL_PREFIX = '/_images/'


class UnsupportedImageError(Exception):
    """받는 형식(PNG, JPEG, WebP)이 아니다."""


class ImageNotFoundError(Exception):
    """그런 그림이 없다. 볼 수 없는 그림도 이것이다."""


def image_url(image_id: uuid.UUID) -> str:
    """그 그림을 내주는 주소."""
    return f'{IMAGES_PATH}/{image_id}'


def detect_format(data: bytes) -> ImageFormat:
    """파일의 머리로 형식을 고른다. 받는 형식이 아니면 UnsupportedImageError."""
    image_format = check_image_header(data)
    if image_format is None:
        raise UnsupportedImageError
    return image_format


def build_image(owner_id: uuid.UUID, image_format: ImageFormat, decoded: DecodedImage) -> Image:
    """다시 인코딩한 그림의 행. 아직 저장하지 않는다."""
    return Image(
        id=uuid.uuid4(),
        owner_id=owner_id,
        format=image_format,
        byte_size=len(decoded.data),
        width=decoded.width,
        height=decoded.height,
    )


async def upload_image(
    session: AsyncSession,
    store: ImageStore,
    decoder: ImageDecoder,
    owner_id: uuid.UUID,
    data: bytes,
    now: datetime,
) -> Image:
    """
    그림을 올린다. 형식이 아니면 UnsupportedImageError, 열 수 없으면 ImageUnreadableError,
    저장소에 넣지 못하면 ImageStoreUnavailableError 다.
    """
    image_format = detect_format(data)
    decoded = await decoder.decode(data, image_format)
    image = build_image(owner_id, image_format, decoded)
    await store.put(str(image.id), decoded.data, CONTENT_TYPES[image_format], now)
    await repository.add_image(session, image)
    await session.commit()
    return image


def can_view(image: Image, viewer_id: uuid.UUID | None) -> bool:
    """이 사람이 그 그림을 볼 수 있나. 지금은 주인만이다."""
    return viewer_id is not None and image.owner_id == viewer_id


async def viewable_image(session: AsyncSession, viewer_id: uuid.UUID | None, image_id: uuid.UUID) -> Image:
    """볼 수 있는 그림. 없거나 볼 수 없으면 ImageNotFoundError."""
    image = await repository.get_image(session, image_id)
    if image is None or not can_view(image, viewer_id):
        raise ImageNotFoundError
    return image


def accel_headers(store: ImageStore, image: Image, now: datetime) -> dict[str, str]:
    """nginx 에 넘기는 머리말. 내부 위치와 저장소의 서명한 주소다. 저장소가 없으면 ImageStoreUnavailableError."""
    return {
        'X-Accel-Redirect': f'{ACCEL_PREFIX}{image.id}',
        'X-Image-Source': store.presigned_get(str(image.id), now),
    }
