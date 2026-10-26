# story-server/tests/test_illustrations.py

"""
행동 뒤에 계정에 남길 일러스트를 고르는 것(app/records/illustrations.py)을 검증한다. 순수 함수라 DB 도 앱도 없다.

보는 것.
  - 해금 대상이고 그림이 있는 장면만 남긴다. 장면이 부르는 인물을 함께 적는다
  - 해금 대상이어도 그림이 없으면, 그림이 있어도 해금 대상이 아니면 남기지 않는다
  - 이벤트와 그 이벤트로 본 엔딩이 함께면 둘 다, 이벤트, 엔딩의 차례다
"""

import uuid

from app.engine.world import Ending, Event
from app.records.illustrations import SceneKind, Unlock, unlocked_scenes
from tests.engine_worlds import ending, event

PICTURE = uuid.UUID('aaaaaaaa-1111-4222-8333-444444444444')
FAREWELL_PICTURE = uuid.UUID('bbbbbbbb-1111-4222-8333-444444444444')


def scene_event(event_id: str, image_id: uuid.UUID | None, collectible: bool, cast: list[str]) -> Event:
    body = event(event_id, cast=cast)
    body['scene'] |= {'image_id': str(image_id) if image_id else None, 'collectible': collectible}
    return Event.model_validate(body)


def scene_ending(ending_id: str, image_id: uuid.UUID | None, collectible: bool) -> Ending:
    body = ending(ending_id, 'event', ending_id)
    body['scene'] |= {'image_id': str(image_id) if image_id else None, 'collectible': collectible}
    return Ending.model_validate(body)


def test_a_collectible_scene_with_a_picture_is_kept_with_its_cast():
    beach = scene_event('beach', PICTURE, True, ['mina', 'jun'])

    assert unlocked_scenes(beach, None) == (Unlock(SceneKind.EVENT, 'beach', PICTURE, ('mina', 'jun')),)


def test_a_scene_without_a_picture_or_not_collectible_is_not_kept():
    no_picture = scene_event('rain', None, True, ['mina'])
    not_collectible = scene_ending('solo', PICTURE, False)

    assert unlocked_scenes(no_picture, not_collectible) == ()


def test_an_event_and_its_ending_are_both_kept_in_order():
    farewell = scene_event('farewell', PICTURE, True, [])
    parting = scene_ending('parting', FAREWELL_PICTURE, True)

    assert unlocked_scenes(farewell, parting) == (
        Unlock(SceneKind.EVENT, 'farewell', PICTURE, ()),
        Unlock(SceneKind.ENDING, 'parting', FAREWELL_PICTURE, ()),
    )


def test_nothing_opened_keeps_nothing():
    assert unlocked_scenes(None, None) == ()
