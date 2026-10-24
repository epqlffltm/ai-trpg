# chat-server/app/world/sprites.py

"""
지금 띄울 캐릭터 그림을 고른다. DB 를 모르는 순수 함수다(asset 의 판 형식 6, 2026-10-23).

그림은 셋이다. 캐릭터 그림(배경이 투명한 서 있는 그림), 배경, 이벤트 씬. 보통의 장면은 배경 위에 캐릭터 그림을 겹친다.
캐릭터 그림은 표정과 차림마다 여럿이다.
  - 차림: 상대가 입은 옷(상태의 outfit) 가운데 가장 나중에 입은 것부터, 그 차림의 그림이 있는 것.
    없으면 처음 차림(outfit 이 빈 것)
  - 표정: 그 차림에서 답의 표정(모델이 고른 것, conversation_core/expressions.py)의 그림. 없으면 기본 표정(빈 글),
    기본 표정의 그림도 없으면 그 차림의 첫 그림
  - 그림이 하나도 맞지 않으면 None(화면은 대표 그림이나 캐릭터 없이 그린다)
모델이 고를 수 있는 표정은 지금 차림에 그림이 있는 표정이다(expression_images).
화면이 같은 규칙을 다시 짜지 않게 서버가 고른 것을 상태의 응답과 SSE 에 싣는다.
"""

import uuid

from app.assets.schemas import CharacterDocument, SpriteDocument
from app.world.state import WorldState

# 기본 표정
BASE_EXPRESSION = ''


def dressed_sprites(document: CharacterDocument, outfit: str | None) -> list[SpriteDocument]:
    """그 차림의 그림들(판의 차례)."""
    return [sprite for sprite in document.sprites if sprite.outfit == outfit]


def current_outfit_sprites(document: CharacterDocument, state: WorldState) -> list[SpriteDocument]:
    """지금 차림의 그림들. 가장 나중에 입은 옷부터 그림이 있는 차림을 찾고, 없으면 처음 차림이다."""
    for outfit in reversed(state.outfit):
        dressed = dressed_sprites(document, outfit)
        if dressed:
            return dressed
    return dressed_sprites(document, None)


def pick_sprite(sprites: list[SpriteDocument], expression: str | None) -> SpriteDocument | None:
    """한 차림의 그림들에서 그 표정의 그림. 없으면 기본 표정, 그것도 없으면 첫 그림, 그림이 없으면 None."""
    wanted = (expression or BASE_EXPRESSION).casefold()
    for target in (wanted, BASE_EXPRESSION):
        found = next((sprite for sprite in sprites if sprite.expression.casefold() == target), None)
        if found is not None:
            return found
    return sprites[0] if sprites else None


def current_sprite(
    document: CharacterDocument, state: WorldState, expression: str | None = None
) -> SpriteDocument | None:
    """지금 띄울 캐릭터 그림. 지금 차림에서 그 표정(없으면 기본)의 그림이다."""
    return pick_sprite(current_outfit_sprites(document, state), expression)


def sprite_image(document: CharacterDocument, state: WorldState, expression: str | None = None) -> uuid.UUID | None:
    """지금 띄울 캐릭터 그림의 그림 id. 없으면 None."""
    sprite = current_sprite(document, state, expression)
    return sprite.image_id if sprite is not None else None


def expression_images(document: CharacterDocument, state: WorldState) -> dict[str, uuid.UUID]:
    """모델이 고를 수 있는 표정(지금 차림에 그림이 있는, 기본이 아닌 것)과 그 그림. 판의 차례다."""
    return {
        sprite.expression: sprite.image_id
        for sprite in current_outfit_sprites(document, state)
        if sprite.expression != BASE_EXPRESSION
    }
