# asset-server/app/images/service.py

"""
그림을 올리고 내준다(#566, docs/architecture/asset-server.md 의 "그림").

올리기: 형식을 머리로 고른다 → 따로 된 프로세스에서 열어 다시 인코딩한다 → 저장소에 넣는다 → 행을 적는다.
  - DB 연결은 맨 끝(행을 적을 때)에만 잡는다. 여는 일과 저장소에 넣는 일은 몇 초가 걸릴 수 있다.
  - 저장소에 넣은 뒤 행을 적지 못하면 저장소에 주인 없는 객체가 남는다. 아무도 가리키지 않아 내주지 않는다.
    반대 차례(행 먼저)면 바이트가 없는 그림을 가리키는 행이 남는다. 앞쪽이 덜 해롭다.
내주기: 볼 수 있으면 본문 없이 X-Accel-Redirect 와 X-Image-Source(저장소의 서명한 주소)를 답한다. nginx 가 받아 내준다.
  - 볼 수 있는 사람: 주인, 그리고 그 그림이 쓰인 판이 공개 캐릭터의 것이고 그 판의 등급을 볼 수 있는 사람
    (로그인하지 않아도 전체 이용가는 본다). 볼 수 없으면 없는 그림과 같다(404).
붙이기: 페르소나와 캐릭터의 대표 그림, 소개 글의 그림은 자기 그림이어야 한다. 남의 그림 id 를 적어 그 그림을 공개로
  돌리는 길을 막는다. 초안에 붙일 때(require_own_images)와 게시할 때(foreign_ids) 본다.
지우기(탈퇴): 그 사람의 그림 가운데 어느 판에도 쓰이지 않은 것을 저장소에서 먼저 지우고, 그다음 행을 지운다.
  저장소에서 지우다 실패하면 행이 남아 다시 온 알림이 다시 지운다. 남이 쓰는 공개 캐릭터의 그림은 남는다.

HTTP 를 모른다. 예외로 알리고 라우터가 응답으로 바꾼다.
"""

import uuid
from collections.abc import Collection
from datetime import datetime

from server_core.auth.tokens import AccessClaims
from sqlalchemy.ext.asyncio import AsyncSession

from app.images import repository
from app.images.formats import CONTENT_TYPES, ImageFormat, check_image_header
from app.images.isolation import DecodedImage, ImageDecoder
from app.images.models import Image
from app.images.store import ImageStore
from app.ratings import allowed_ratings

# 그림을 내주는 주소. 소개 글의 img 가 이 모양만 받는다(app/content/html.py 의 IMAGE)
IMAGES_PATH = '/api/v1/asset/images'
# nginx 의 내부 위치(docker/nginx/templates/api.inc.template 의 /_images/)
ACCEL_PREFIX = '/_images/'


class UnsupportedImageError(Exception):
    """받는 형식(PNG, JPEG, WebP)이 아니다."""


class ImageNotFoundError(Exception):
    """그런 그림이 없다. 볼 수 없는 그림도 이것이다."""


class ImageNotOwnedError(Exception):
    """붙이려는 그림이 이 사람의 것이 아니다. 없는 그림도 이것이다."""


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


async def can_view(session: AsyncSession, image: Image, viewer: AccessClaims | None) -> bool:
    """이 사람이 그 그림을 볼 수 있나. 주인이거나, 그 그림이 쓰인 공개 캐릭터나 공개 세계관의 판의 등급을 볼 수 있다."""
    if viewer is not None and image.owner_id == viewer.user_id:
        return True
    return await repository.used_publicly(session, image.id, allowed_ratings(viewer))


async def viewable_image(session: AsyncSession, viewer: AccessClaims | None, image_id: uuid.UUID) -> Image:
    """볼 수 있는 그림. 없거나 볼 수 없으면 ImageNotFoundError."""
    image = await repository.get_image(session, image_id)
    if image is None or not await can_view(session, image, viewer):
        raise ImageNotFoundError
    return image


async def foreign_ids(session: AsyncSession, owner_id: uuid.UUID, image_ids: Collection[uuid.UUID]) -> list[uuid.UUID]:
    """그 id 들 가운데 이 사람의 그림이 아닌 것(없는 것 포함). 받은 차례다."""
    owned = await repository.owned_ids(session, owner_id, image_ids)
    return [image_id for image_id in image_ids if image_id not in owned]


async def require_own_images(session: AsyncSession, owner_id: uuid.UUID, image_ids: Collection[uuid.UUID]) -> None:
    """모두 이 사람의 그림이어야 한다. 아니면 ImageNotOwnedError."""
    if await foreign_ids(session, owner_id, image_ids):
        raise ImageNotOwnedError


def record_uses(session: AsyncSession, version_id: uuid.UUID, image_ids: Collection[uuid.UUID]) -> None:
    """그 판에 쓰인 그림들을 적는다. 커밋하지 않는다(게시와 한 트랜잭션이다)."""
    repository.add_uses(session, version_id, image_ids)


def record_world_uses(session: AsyncSession, version_id: uuid.UUID, image_ids: Collection[uuid.UUID]) -> None:
    """그 세계관의 판에 쓰인 그림들을 적는다(#591). 커밋하지 않는다(게시와 한 트랜잭션이다)."""
    repository.add_world_uses(session, version_id, image_ids)


async def erase_images(session: AsyncSession, store: ImageStore, owner_id: uuid.UUID, now: datetime) -> None:
    """
    그 사람의 그림 가운데 어느 판에도 쓰이지 않은 것을 지운다. 저장소 먼저, 행은 나중이다.

    저장소를 부르는 동안 DB 연결을 잡지 않는다(찾은 뒤 트랜잭션을 끝낸다).
    저장소에서 지우지 못하면 ImageStoreUnavailableError 이고 행은 남는다. 다시 부르면 다시 지운다.
    """
    image_ids = await repository.unused_owned_ids(session, owner_id)
    await session.commit()
    for image_id in image_ids:
        await store.delete(str(image_id), now)
    await repository.delete_unused(session, image_ids)
    await session.commit()


def accel_headers(store: ImageStore, image: Image, now: datetime) -> dict[str, str]:
    """nginx 에 넘기는 머리말. 내부 위치와 저장소의 서명한 주소다. 저장소가 없으면 ImageStoreUnavailableError."""
    return {
        'X-Accel-Redirect': f'{ACCEL_PREFIX}{image.id}',
        'X-Image-Source': store.presigned_get(str(image.id), now),
    }
