# trpg-server/app/free_rolls/schemas.py

"""
자유 굴림 API(#404)가 받는 입력과 내보내는 응답의 모양.

주사위 설명은 받을 때 읽어 본다(app/engine/dice_notation.py). 받는 모양이 아니면 422 다.
"""

import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from app.engine import dice_notation


def readable(text: str) -> str:
    """주사위 설명을 읽어 보고, 다시 쓴 설명을 돌려준다. 받는 모양이 아니면 ValueError(422)."""
    try:
        return dice_notation.parse(text).text
    except dice_notation.NotationError as error:
        raise ValueError(f'주사위 설명을 읽지 못했습니다({error.reason}). 예: d20, 2d6+1') from error


DiceText = Annotated[str, StringConstraints(max_length=dice_notation.MAX_LENGTH), AfterValidator(readable)]


class FreeRollCreate(BaseModel):
    """자유 굴림을 할 때 받는 값. 굴리는 사람은 토큰에서 읽는다. 눈은 서버가 굴린다. 받지 않는다."""

    model_config = ConfigDict(extra='forbid')

    # 주사위 설명. [개수]d면수[+보정]. 면 수는 4, 6, 8, 10, 12, 20, 100. 개수는 10 까지, 보정은 ±100 까지
    dice: DiceText


class FreeRollOut(BaseModel):
    """
    자유 굴림 한 번. 같은 내용이 이벤트(dice_rolled)로 모두에게 간다.

    게임의 상태와 무관하다. 판정도 피해도 아니고, 서술하는 AI 도 받지 않는다.
    """

    # 이 굴림을 적은 이벤트의 번호. 이벤트의 흐름에서 같은 굴림을 찾을 때 쓴다
    sequence: int
    user_id: uuid.UUID
    character_name: str | None
    # 다시 쓴 주사위 설명("2d6+1")
    dice: str
    # 굴린 눈들. 굴린 순서다
    faces: list[int]
    bonus: int
    # 눈들의 합 + 보정
    total: int
