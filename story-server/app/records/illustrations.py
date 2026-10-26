# story-server/app/records/illustrations.py

"""
행동 하나 뒤에 계정에 남길 일러스트를 고른다(docs/architecture/story.md 의 "일러스트 열기"). DB 를 모른다.

일러스트는 이벤트와 엔딩의 장면(Scene)에 붙어 있다. 장면이 해금 대상(collectible)이고 그림(image_id)이 있으면 남긴다.
asset 서버가 게시할 때 해금 대상에 그림이 있는지 본다. 그래도 그림이 없는 장면은 남기지 않는다(보일 것이 없다).
한 행동이 이벤트를 열고 그 이벤트로 엔딩을 볼 수 있다. 그때는 둘 다다(이벤트, 엔딩의 차례).
"""

import enum
import uuid
from dataclasses import dataclass

from app.engine.world import Ending, Event, Scene


class SceneKind(enum.StrEnum):
    """일러스트가 붙은 장면의 종류. 이벤트와 엔딩의 id 는 서로 겹칠 수 있어 종류로 가른다."""

    EVENT = 'event'
    ENDING = 'ending'


@dataclass(frozen=True)
class Unlock:
    """남길 일러스트 하나. 장면의 종류와 id, 그림, 그 장면이 부르는 인물들이다."""

    kind: SceneKind
    scene_id: str
    image_id: uuid.UUID
    cast: tuple[str, ...]


def unlock_of(kind: SceneKind, scene_id: str, scene: Scene) -> Unlock | None:
    """그 장면이 남길 일러스트. 해금 대상이 아니거나 그림이 없으면 None."""
    if not scene.collectible or scene.image_id is None:
        return None
    return Unlock(kind=kind, scene_id=scene_id, image_id=scene.image_id, cast=scene.cast)


def unlocked_scenes(event: Event | None, ending: Ending | None) -> tuple[Unlock, ...]:
    """행동 뒤에 열린 이벤트와 본 엔딩 가운데 남길 일러스트들. 이벤트, 엔딩의 차례다."""
    found: list[Unlock | None] = []
    if event is not None:
        found.append(unlock_of(SceneKind.EVENT, event.id, event.scene))
    if ending is not None:
        found.append(unlock_of(SceneKind.ENDING, ending.id, ending.scene))
    return tuple(unlock for unlock in found if unlock is not None)
