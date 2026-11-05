# trpg-server/app/snapshots/references.py

"""
장면 그림의 참고 그림(#983). 앉은 캐릭터가 고른 프리젠에 제작자가 붙인 그림을 그림 모델에 함께 넘겨 얼굴을 맞춘다.

  - 무엇을 넘길지는 테이블의 상태로 고른다(app/portraits/seats.py). 이름이 있고 그림이 있는 캐릭터, 앉은 차례, 4명까지
  - 바이트는 asset 서버에서 서명만으로 받는다. 이 서버가 맡긴 그림이다(제작자가 이 서버로 올렸다)
  - 받지 못한 그림(지워졌다, asset 이 잠시 안 된다)은 빼고 그린다. 참고 그림 때문에 한 장을 실패로 두지 않는다
  - 참고 그림을 받지 않는 provider(로컬의 기본 흐름)에는 받지도 넘기지도 않는다
플레이어가 직접 만든 캐릭터에는 그림이 없다(실제 사람의 사진이 그림 모델에 들어갈 수 있어서 받지 않는다).
"""

import logging
import uuid
from dataclasses import dataclass

from ai_core.image_provider import ImageProvider, ReferenceImage, ReferenceKind

from app.asset_server.client import AssetClient, AssetNotFoundError, AssetUnavailableError
from app.portraits.seats import character_portraits
from app.tables.models import GameTable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReferenceTarget:
    """넘길 참고 그림 하나. name 은 그 그림의 캐릭터다(지시에 "1번째 그림: 엘프"로 쓴다)."""

    name: str
    image_id: uuid.UUID


def character_targets(table: GameTable) -> tuple[ReferenceTarget, ...]:
    """넘길 그림들. 이름과 그림이 있는 캐릭터, 앉은 차례다."""
    pairs = character_portraits(table, table.members)
    return tuple(ReferenceTarget(name=name, image_id=image_id) for name, image_id in pairs)


async def fetch_reference(asset: AssetClient, target: ReferenceTarget) -> ReferenceImage | None:
    """그림 하나의 바이트. 받지 못하면 로그에 남기고 None."""
    try:
        content = await asset.fetch_kept(target.image_id)
    except (AssetNotFoundError, AssetUnavailableError) as error:
        logger.warning(
            '참고 그림을 받지 못해 빼고 그립니다',
            extra={'image_id': str(target.image_id), 'reason': type(error).__name__},
        )
        return None
    return ReferenceImage(data=content.data, mime_type=content.mime_type, kind=ReferenceKind.CHARACTER)


async def fetch_references(
    provider: ImageProvider, asset: AssetClient, targets: tuple[ReferenceTarget, ...]
) -> list[tuple[ReferenceTarget, ReferenceImage]]:
    """넘길 그림들과 그 바이트. 받은 것만 차례대로다. provider 가 참고 그림을 받지 않으면 부르지 않고 비어 있다."""
    if not provider.supports_references:
        return []
    fetched = [(target, await fetch_reference(asset, target)) for target in targets]
    return [(target, image) for target, image in fetched if image is not None]
