# game-server/app/engine/action.py

"""
행동의 모양. 선언에 붙어서 "무엇을 어떻게 하려는지"를 엔진이 읽을 수 있게 한다.

선언의 글("문을 걷어찬다")은 사람과 서술자가 읽는다. 엔진은 글을 읽지 못한다.
엔진이 읽는 것은 행동이다. 어느 능력으로, 어느 난이도로 하는지가 정해진 모양으로 적혀 있다.
나중에 AI 가 하는 일은 글을 이 모양으로 바꿔 제안하는 것이다. 제안은 여기의 검사를 그대로 거친다.

시트와 같이 둘로 나눠 검사한다.
  - 모양(CheckAction): 규칙을 몰라도 볼 수 있는 것. 입력을 받을 때 검사한다.
  - 맞음(find_fault): 그 테이블의 규칙과 견주어야 알 수 있는 것. "근력"이 이 규칙에 있는 능력인가.

지금은 종류가 하나다(판정). 종류를 나타내는 칸(kind)을 처음부터 둔다. 종류가 늘어도 모양이 바뀌지 않는다.
"""

import enum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.engine.check import find_ability, find_difficulty
from app.engine.ruleset import Key, Ruleset


class ActionKind(enum.StrEnum):
    """행동의 종류."""

    # 능력 하나로 난이도 하나에 도전한다. 주사위를 한 번 굴린다
    CHECK = 'check'


class CheckAction(BaseModel):
    """판정을 하는 행동."""

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.CHECK]
    # 판정에 쓰는 능력. 규칙의 Ability.key 다
    ability: Key
    # 난이도의 단계. 규칙의 Difficulty.key 다. 숫자를 직접 받지 않는다.
    # 비우면 규칙의 기본 난이도다
    difficulty: Key | None = None


def find_fault(ruleset: Ruleset, action: CheckAction) -> str | None:
    """
    행동이 이 규칙에 맞지 않으면 틀린 칸의 이름을 돌려준다. 맞으면 None.

    능력과 난이도가 규칙에 있는 것이어야 한다. 난이도를 비웠으면 기본 난이도라 늘 있다.
    """
    if find_ability(ruleset, action.ability) is None:
        return 'ability'
    if find_difficulty(ruleset, action.difficulty) is None:
        return 'difficulty'
    return None


def settle(ruleset: Ruleset, action: CheckAction) -> CheckAction:
    """
    비워 둔 난이도를 규칙의 기본 난이도로 채운 행동을 돌려준다. 받은 행동은 고치지 않는다.

    저장하는 행동에는 늘 난이도가 적혀 있게 한다. 읽는 쪽이 "비어 있으면 기본"을 다시 따지지 않는다.
    find_fault 를 통과한 행동에만 쓴다.
    """
    difficulty = find_difficulty(ruleset, action.difficulty)
    return action.model_copy(update={'difficulty': difficulty.key})
