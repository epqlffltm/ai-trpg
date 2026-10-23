# chat-server/app/world/sprites.py

"""
지금 띄울 캐릭터 그림을 고른다. DB 를 모르는 순수 함수다(asset 의 판 형식 6, 2026-10-23).

그림은 셋이다. 캐릭터 그림(배경이 투명한 서 있는 그림), 배경, 이벤트 씬. 보통의 장면은 배경 위에 캐릭터 그림을 겹친다.
캐릭터 그림은 표정과 차림마다 여럿이다. 지금은 기본 표정(빈 글)만 고른다. 표정을 고르는 것은 다음 단계다
(모델이 응답 끝의 표식으로 고르고 서버가 검증한다).
  - 차림: 상대가 입은 옷(상태의 outfit) 가운데 가장 나중에 입은 것부터, 그 차림의 그림이 있는 것
  - 없으면 처음 차림(outfit 이 빈 것)의 그림
  - 기본 표정의 그림이 없으면 그 차림의 첫 그림
  - 그림이 하나도 맞지 않으면 None(화면은 대표 그림이나 캐릭터 없이 그린다)
화면이 같은 규칙을 다시 짜지 않게 서버가 고른 것을 상태의 응답에 싣는다.
"""

import uuid

from app.assets.schemas import CharacterDocument, SpriteDocument
from app.world.state import WorldState

# 기본 표정
BASE_EXPRESSION = ''


def sprite_for_outfit(document: CharacterDocument, outfit: str | None) -> SpriteDocument | None:
    """그 차림의 그림. 기본 표정을 먼저 고르고, 없으면 그 차림의 첫 그림이다. 그 차림의 그림이 없으면 None."""
    dressed = [sprite for sprite in document.sprites if sprite.outfit == outfit]
    base = next((sprite for sprite in dressed if sprite.expression == BASE_EXPRESSION), None)
    return base or (dressed[0] if dressed else None)


def current_sprite(document: CharacterDocument, state: WorldState) -> SpriteDocument | None:
    """지금 띄울 캐릭터 그림. 가장 나중에 입은 옷의 그림부터 찾고, 없으면 처음 차림의 그림이다."""
    for outfit in reversed(state.outfit):
        found = sprite_for_outfit(document, outfit)
        if found is not None:
            return found
    return sprite_for_outfit(document, None)


def sprite_image(document: CharacterDocument, state: WorldState) -> uuid.UUID | None:
    """지금 띄울 캐릭터 그림의 그림 id. 없으면 None."""
    sprite = current_sprite(document, state)
    return sprite.image_id if sprite is not None else None
