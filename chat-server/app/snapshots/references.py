# chat-server/app/snapshots/references.py

"""
장면 그림의 참고 그림(#983). 제작자가 판에 올린 캐릭터의 그림을 그림 모델에 함께 넘겨 얼굴과 차림을 맞춘다.

  - 무엇을 넘길지는 서버의 상태로 고른다. 지금 차림의 기본 표정 그림, 없으면 캐릭터의 대표 그림이다(하나)
  - 바이트는 asset 서버에서 사용자의 토큰으로 받는다. 그 사람이 볼 수 있는 그림만 받는다
  - 받지 못한 그림(지워졌다, asset 이 잠시 안 된다)은 빼고 그린다. 참고 그림 때문에 한 장을 실패로 두지 않는다
  - 참고 그림을 받지 않는 provider(로컬의 기본 흐름)에는 받지도 넘기지도 않는다
페르소나(사용자 쪽)의 그림은 넘기지 않는다. 실제 사람의 사진일 수 있어서 따로 정할 때까지 뺀다.
"""

import logging
import uuid
from dataclasses import dataclass

from ai_core.image_provider import ImageProvider, ReferenceImage, ReferenceKind

from app.assets.client import AssetClient, AssetNotFoundError, AssetUnavailableError
from app.assets.schemas import CharacterDocument
from app.world.sprites import sprite_image
from app.world.state import WorldState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReferenceTarget:
    """넘길 참고 그림 하나. name 은 그 그림의 인물이다(지시에 "1번째 그림: 세라"로 쓴다)."""

    name: str
    image_id: uuid.UUID


def character_targets(document: CharacterDocument, state: WorldState) -> tuple[ReferenceTarget, ...]:
    """넘길 그림. 지금 차림의 기본 표정 그림, 없으면 대표 그림이다. 둘 다 없으면 비어 있다."""
    image_id = sprite_image(document, state) or document.image_id
    return () if image_id is None else (ReferenceTarget(name=document.name.strip(), image_id=image_id),)


async def fetch_reference(asset: AssetClient, token: str, target: ReferenceTarget) -> ReferenceImage | None:
    """그림 하나의 바이트. 받지 못하면 로그에 남기고 None."""
    try:
        content = await asset.fetch_image(token, target.image_id)
    except (AssetNotFoundError, AssetUnavailableError) as error:
        logger.warning(
            '참고 그림을 받지 못해 빼고 그립니다',
            extra={'image_id': str(target.image_id), 'reason': type(error).__name__},
        )
        return None
    return ReferenceImage(data=content.data, mime_type=content.mime_type, kind=ReferenceKind.CHARACTER)


async def fetch_references(
    provider: ImageProvider, asset: AssetClient, token: str, targets: tuple[ReferenceTarget, ...]
) -> list[tuple[ReferenceTarget, ReferenceImage]]:
    """넘길 그림들과 그 바이트. 받은 것만 차례대로다. provider 가 참고 그림을 받지 않으면 부르지 않고 비어 있다."""
    if not provider.supports_references:
        return []
    fetched = [(target, await fetch_reference(asset, token, target)) for target in targets]
    return [(target, image) for target, image in fetched if image is not None]
