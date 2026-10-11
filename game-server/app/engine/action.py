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

행동을 실제로 하는 것도 여기 있다(attempt). 라운드가 선언을 마감할 때 부른다.

행동에는 판정의 결과에 따라 일어날 일을 붙일 수 있다.
  - 실패의 대가(risk): 실패하면 행동한 캐릭터가 피해를 입는다.
  - 성공의 보상(recover): 성공하면 대상이 회복한다. 대상은 앉은 사람(target)이나 NPC(npc)다.
  - 성공의 타격(harm): 성공하면 대상 NPC(npc)가 피해를 입는다. 앉은 사람끼리는 해치지 않는다.
양은 모두 숫자로 받지 않고 규칙의 등급으로 받는다. 어느 것이 일어나는지는 consequence 가 정한다.
타격에는 죽이려는지(lethal)를 적는다. HP 가 0 이 됐을 때 쓰러질지 죽을지를 가른다(app/tables/npcs.py).
타격에는 노릴 부상(aim)도 적을 수 있다(노려 치기). 판정이 어려워지고, 성공하면 그 부상이 확정으로 생긴다.
얼마나 어려워지는지는 규칙이 정한다(Ruleset.called_shot). 노릴 수 있는 부상도 규칙이 표시한 것뿐이다.
"""

import enum
import uuid
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.engine.check import Check, HinderedCheck, find_ability, find_difficulty, resolve_hindered
from app.engine.dice import Dice
from app.engine.health import ChangeKind, find_magnitude
from app.engine.injury import NO_HINDRANCE, Hindrance, find_injury
from app.engine.ruleset import CalledShotMode, Key, Ruleset


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

    # 실패의 대가. 실패하면 행동한 캐릭터가 이 등급만큼 피해를 입는다. 규칙의 Magnitude.key 다.
    # 비우면 실패해도 다치지 않는다
    risk: Key | None = None
    # 성공의 보상. 성공하면 대상이 이 등급만큼 회복한다. 규칙의 Magnitude.key 다
    recover: Key | None = None
    # 회복하는 대상. 테이블에 앉은 사람이다. 엔진은 이 값을 읽지 않는다. 누구인지는 부른 쪽이 안다.
    # recover 가 있는데 target 도 npc 도 비우면 자기 자신이다(app/rounds/service.py 가 채운다)
    target: uuid.UUID | None = None

    # 성공의 타격. 성공하면 대상 NPC 가 이 등급만큼 피해를 입는다. 규칙의 Magnitude.key 다
    harm: Key | None = None
    # 대상 NPC. 판의 로어북 인물 항목의 id 다. 이번 장면에 나온 인물만 고를 수 있다(app/rounds/cast.py).
    # 엔진은 이 값을 읽지 않는다
    npc: uuid.UUID | None = None
    # 타격이 죽이려는 것인가. 아니면 제압이다. HP 가 0 이 되면 제압은 쓰러뜨리고, 죽이려는 것은 죽인다
    lethal: bool = False
    # 노려 치기. 노릴 부상의 이름표(규칙의 Injury.key)다. 판정이 어려워지고, 성공하면 그 부상을 입힌다.
    # 그 타격에서는 부상 표를 굴리지 않는다
    aim: Key | None = None

    @model_validator(mode='after')
    def require_recover_for_target(self) -> Self:
        """대상(앉은 사람)은 회복에만 쓴다. 회복이 없는데 대상만 있으면 무엇을 하려는지 알 수 없다."""
        if self.target is not None and self.recover is None:
            raise ValueError('target 은 recover 와 함께 적습니다.')
        return self

    @model_validator(mode='after')
    def require_one_target(self) -> Self:
        """대상은 하나다. 앉은 사람과 NPC 를 함께 적지 않는다."""
        if self.target is not None and self.npc is not None:
            raise ValueError('target 과 npc 는 함께 적지 않습니다.')
        return self

    @model_validator(mode='after')
    def require_npc_for_harm(self) -> Self:
        """
        타격과 NPC 는 함께 있다. 타격에는 맞을 NPC 가 있어야 하고, NPC 에게는 무엇을 할지가 있어야 한다.

        NPC 에게 하는 일은 타격이나 회복이다. 둘을 함께 붙이지 않는다. 성공하면 둘 중 하나만 일어날 수 있다.
        죽이려는지는 타격에만 뜻이 있다.
        """
        if self.harm is not None and self.npc is None:
            raise ValueError('harm 은 npc 와 함께 적습니다.')
        if self.npc is not None and self.harm is None and self.recover is None:
            raise ValueError('npc 는 harm 이나 recover 와 함께 적습니다.')
        if self.harm is not None and self.recover is not None:
            raise ValueError('harm 과 recover 는 함께 적지 않습니다.')
        if self.lethal and self.harm is None:
            raise ValueError('lethal 은 harm 과 함께 적습니다.')
        if self.aim is not None and self.harm is None:
            raise ValueError('aim 은 harm 과 함께 적습니다.')
        return self


class Recipient(enum.StrEnum):
    """판정의 결과를 받는 쪽."""

    # 행동한 캐릭터. 실패의 대가를 입는다
    ACTOR = 'actor'
    # 행동의 대상(앉은 사람이나 NPC). 성공의 보상과 타격을 받는다
    TARGET = 'target'


@dataclass(frozen=True)
class Consequence:
    """판정의 결과로 일어나는 일. 방향, 양의 등급, 받는 쪽이다."""

    kind: ChangeKind
    magnitude: Key
    recipient: Recipient


def find_fault(ruleset: Ruleset, action: CheckAction) -> str | None:
    """
    행동이 이 규칙에 맞지 않으면 틀린 칸의 이름을 돌려준다. 맞으면 None.

    능력, 난이도, 양의 등급이 규칙에 있는 것이어야 한다. 난이도를 비웠으면 기본 난이도라 늘 있다.
    대상이 테이블에 앉은 사람인지, 이번 장면의 인물인지는 여기서 보지 않는다. 규칙이 아니라 테이블을 봐야 알 수 있다.
    """
    if find_ability(ruleset, action.ability) is None:
        return 'ability'
    if find_difficulty(ruleset, action.difficulty) is None:
        return 'difficulty'
    if action.risk is not None and find_magnitude(ruleset, action.risk) is None:
        return 'risk'
    if action.recover is not None and find_magnitude(ruleset, action.recover) is None:
        return 'recover'
    if action.harm is not None and find_magnitude(ruleset, action.harm) is None:
        return 'harm'
    if action.aim is not None and not can_aim(ruleset, action.aim):
        return 'aim'
    return None


def can_aim(ruleset: Ruleset, key: str) -> bool:
    """이 규칙에서 이 부상을 노려 칠 수 있는가. 노려 치기를 켰고, 그 부상이 노릴 수 있다고 표시돼 있어야 한다."""
    if not ruleset.injury_triggers.called_shot or ruleset.called_shot is None:
        return False
    injury = find_injury(ruleset, key)
    return injury is not None and injury.aimable


def called_shot_terms(ruleset: Ruleset, action: CheckAction) -> tuple[int, bool]:
    """
    노려 치기가 판정을 어렵게 하는 만큼. (목표값을 올리는 양, 불리한가) 다. 노려 치지 않으면 (0, False).

    받을 때 노릴 수 있는지 본 행동(find_fault)에만 쓴다.
    """
    if action.aim is None or ruleset.called_shot is None:
        return 0, False
    shot = ruleset.called_shot
    if shot.mode == CalledShotMode.TARGET_PLUS:
        return shot.amount, False
    return 0, True


def settle(ruleset: Ruleset, action: CheckAction) -> CheckAction:
    """
    비워 둔 난이도를 규칙의 기본 난이도로 채운 행동을 돌려준다. 받은 행동은 고치지 않는다.

    저장하는 행동에는 늘 난이도가 적혀 있게 한다. 읽는 쪽이 "비어 있으면 기본"을 다시 따지지 않는다.
    find_fault 를 통과한 행동에만 쓴다.
    """
    difficulty = find_difficulty(ruleset, action.difficulty)
    return action.model_copy(update={'difficulty': difficulty.key})


def attempt(ruleset: Ruleset, action: CheckAction, abilities: dict[str, int], dice: Dice) -> Check:
    """
    행동을 한다. 판정을 한 번 하고 그 결과를 돌려준다. 주사위를 한 번 굴린다. 부상의 영향이 없는 판정이다.

    abilities 는 행동하는 캐릭터의 시트에 적힌 능력치의 점수다({능력의 key: 점수}).
    """
    return attempt_hindered(ruleset, action, abilities, dice, NO_HINDRANCE).check


def attempt_hindered(
    ruleset: Ruleset, action: CheckAction, abilities: dict[str, int], dice: Dice, hindrance: Hindrance
) -> HinderedCheck:
    """
    부상을 입은 캐릭터가 행동을 한다. 판정을 한 번 하고 그 결과를 돌려준다.

    hindrance 는 그 캐릭터의 부상이 이 행동의 능력에 주는 것이다(app/engine/injury.py 의 hindrance_of).
    노려 치면 규칙이 정한 만큼 어려워진다. 목표값이 오르거나(판정의 target 이 오른 값이다), 불리하다.

    받을 때 규칙에 맞는지 본 행동(find_fault, settle)과, 같은 규칙으로 검사한 시트에만 쓴다.
    그래서 여기서는 능력과 난이도가 있는지 다시 따지지 않는다.
    """
    difficulty = find_difficulty(ruleset, action.difficulty)
    raise_by, aim_disadvantage = called_shot_terms(ruleset, action)
    if raise_by:
        difficulty = difficulty.model_copy(update={'target': difficulty.target + raise_by})
    score = abilities[action.ability]
    return resolve_hindered(ruleset, score, difficulty, dice, hindrance, forced_disadvantage=aim_disadvantage)


def consequence(action: CheckAction, check: Check) -> Consequence | None:
    """
    판정의 결과에 따라 일어나는 일을 돌려준다. 아무 일도 없으면 None.

    실패했고 대가가 붙어 있으면 행동한 캐릭터의 피해, 성공했고 타격이 붙어 있으면 대상의 피해,
    성공했고 보상이 붙어 있으면 대상의 회복이다. 타격과 보상은 함께 붙지 않는다(CheckAction).
    한 판정에서 둘이 함께 일어나지 않는다. 성공과 실패는 함께 일어나지 않기 때문이다.
    대상이 앉은 사람인지 NPC 인지는 행동에 적혀 있다. 엔진은 그것을 가리지 않는다.
    """
    if not check.success and action.risk is not None:
        return Consequence(ChangeKind.DAMAGE, action.risk, Recipient.ACTOR)
    if check.success and action.harm is not None:
        return Consequence(ChangeKind.DAMAGE, action.harm, Recipient.TARGET)
    if check.success and action.recover is not None:
        return Consequence(ChangeKind.RECOVERY, action.recover, Recipient.TARGET)
    return None
