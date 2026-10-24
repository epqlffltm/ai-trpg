# trpg-server/app/engine/action.py

"""
행동의 모양. 선언에 붙어서 "무엇을 어떻게 하려는지"를 엔진이 읽을 수 있게 한다.

선언의 글("문을 걷어찬다")은 사람과 서술자가 읽는다. 엔진은 글을 읽지 못한다.
엔진이 읽는 것은 행동이다. 어느 능력으로, 어느 난이도로 하는지가 정해진 모양으로 적혀 있다.
나중에 AI 가 하는 일은 글을 이 모양으로 바꿔 제안하는 것이다. 제안은 여기의 검사를 그대로 거친다.

시트와 같이 둘로 나눠 검사한다.
  - 모양(CheckAction): 규칙을 몰라도 볼 수 있는 것. 입력을 받을 때 검사한다.
  - 맞음(find_fault): 그 테이블의 규칙과 견주어야 알 수 있는 것. "근력"이 이 규칙에 있는 능력인가.

종류는 열여섯이다. 판정(check), 치료(treat), 지목(name), 물건 쓰기(use), 물건 건네기(give), 가기(move), 찾기(search),
쉬기(rest), 줍기(take), 내려놓기(put_down), 훔치기(steal), 빼앗기(loot), 기다리기(wait), 사기(buy), 팔기(sell),
돈 건네기(pay).
종류를 나타내는 칸(kind)으로 가른다(Action).
치료는 능력과 난이도를 받지 않는다. 규칙이 정한다(app/engine/treatment.py).
지목은 주사위를 굴리지 않는다. 짚은 이름이 정답인지만 본다(app/rounds/naming.py).
쓰기와 건네기도 판정이 없다. 소지품을 바꾸고, 회복하는 소모품이면 회복의 주사위만 굴린다(app/rounds/item_actions.py).
가기는 판정이 없다. 이웃한 장소로 한 칸 간다. 찾기는 그 장소의 숨긴 길과 숨긴 물건마다 판의 판정을 굴린다
(app/rounds/map_actions.py). 줍기는 판정이 없다. 그 장소에 보이게 놓인 물건을 가져간다
(app/rounds/place_item_actions.py). 내려놓기도 판정이 없다. 가진 물건을 그 장소에 보이게 둔다.
훔치기는 규칙이 정한 능력과 목표값으로 한 번 굴린다. 목표값은 물건과 대상에 따라 오르내린다(app/rounds/steals.py).
쉬기는 판정이 없다. 쉬는 라운드가 그 휴식의 시간만큼 이어지고, 라운드가 닫힐 때 다치지 않았으면 회복한다
(app/rounds/rests.py).
기다리기도 판정이 없다. 앉은 사람이 모두 기다리면 가장 짧게 부른 시간만큼 흐른다(app/rounds/waits.py).
사기, 팔기, 돈 건네기도 판정이 없다. 값은 판이 정하고, 돈과 소지품을 엔진이 옮긴다(app/rounds/trades.py, #278).

행동을 실제로 하는 것도 여기 있다(attempt). 라운드가 선언을 마감할 때 부른다.

행동에는 판정의 결과에 따라 일어날 일을 붙일 수 있다.
  - 실패의 대가(risk): 실패하면 행동한 캐릭터가 피해를 입는다.
  - 성공의 보상(recover): 성공하면 대상이 회복한다. 대상은 앉은 사람(target)이나 NPC(npc)다.
  - 성공의 타격(harm): 성공하면 대상 NPC(npc)나 몬스터 한 마리(monster)가 피해를 입는다. 앉은 사람끼리는 해치지 않는다.
양은 모두 숫자로 받지 않고 규칙의 등급으로 받는다. 어느 것이 일어나는지는 consequence 가 정한다.
타격에는 죽이려는지(lethal)를 적는다. HP 가 0 이 됐을 때 쓰러질지 죽을지를 가른다(app/tables/npcs.py).
타격에는 노릴 부상(aim)도 적을 수 있다(노려 치기). 판정이 어려워지고, 성공하면 그 부상이 확정으로 생긴다.
얼마나 어려워지는지는 규칙이 정한다(Ruleset.called_shot). 노릴 수 있는 부상도 규칙이 표시한 것뿐이다.
타격에는 쓰는 무기(weapon, 착용한 물건)와 노릴 부위(strike, 장비의 칸)도 적을 수 있다(#276).
무기는 그 공격 보정만큼 판정의 보정을 올린다. 부위를 노리면 노려 치기와 같은 대가를 치르고, 부위를 굴리지 않는다.
부위의 방어가 무엇을 하는지는 규칙의 방어 방식이 정한다(app/engine/armor.py).
"""

import enum
import uuid
from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, model_validator

from app.engine import armor
from app.engine.check import Check, HinderedCheck, find_ability, find_difficulty, resolve_hindered
from app.engine.dice import Dice
from app.engine.health import ChangeKind, find_magnitude
from app.engine.injury import NO_HINDRANCE, Hindrance, find_injury
from app.engine.ruleset import CalledShotMode, Key, Ruleset
from app.engine.treatment import treatable


class ActionKind(enum.StrEnum):
    """행동의 종류."""

    # 능력 하나로 난이도 하나에 도전한다. 주사위를 한 번 굴린다
    CHECK = 'check'
    # 오래 가는 부상 하나를 치료한다. 규칙이 정한 능력과 난이도로 주사위를 한 번 굴린다
    TREAT = 'treat'
    # 인물의 진짜 이름을 짚는다. 주사위를 굴리지 않는다
    NAME = 'name'
    # 가진 소모품 하나를 쓴다. 회복하는 것이면 대상이 그만큼 회복한다
    USE = 'use'
    # 가진 물건을 앉은 다른 사람에게 건넨다
    GIVE = 'give'
    # 맵에서 지금 장소와 아는 길로 이어진 장소로 한 칸 간다
    MOVE = 'move'
    # 지금 장소에서 숨긴 길과 숨긴 물건을 찾는다. 하나하나 판에 적힌 판정을 굴린다
    SEARCH = 'search'
    # 쉰다. 짧게(short) 또는 길게(long). 쉬는 시간과 회복량은 규칙이 정한다
    REST = 'rest'
    # 지금 장소에 보이게 놓인 물건을 줍는다
    TAKE = 'take'
    # 가진 물건을 지금 장소에 내려놓는다. 누구나 주울 수 있게 보이게 놓인다
    PUT_DOWN = 'put_down'
    # 같은 장소의 몬스터 한 마리나 장면의 인물이 지닌 물건 하나를 훔친다. 규칙이 정한 능력으로 한 번 굴린다
    STEAL = 'steal'
    # 쓰러졌거나 죽은 몬스터나 인물이 지닌 물건 하나를 가져간다. 굴리지 않는다
    LOOT = 'loot'
    # 시간을 건너뛴다("사흘 기다린다"). 모두가 기다려야 흐른다
    WAIT = 'wait'
    # 장면의 상인에게서 물건을 산다. 판에 적힌 값을 낸다(#278)
    BUY = 'buy'
    # 장면의 상인에게 가진 물건을 판다. 판에 적힌 값에 화폐의 백분율을 곱해 받는다(#278)
    SELL = 'sell'
    # 가진 돈을 앉은 다른 사람에게 건넨다(#278)
    PAY = 'pay'
    # 지금 장소의 숨을 곳에 엄폐한다. 그 라운드 동안 그 장소의 커버로 커버 세이브를 받는다(#276). 세이브 방식에서만
    COVER = 'cover'
    # 지금 장소에 닿은 길의 문을 잠근다. 자물쇠는 그 열쇠로, 빗장은 빗장 쪽에서 건다(#281)
    LOCK = 'lock'
    # 지금 장소에 닿은 길의 문을 연다. 자물쇠는 그 열쇠로, 빗장은 빗장 쪽에서 푼다(#281)
    UNLOCK = 'unlock'
    # 지금 장소에 닿은 길의 잠긴 자물쇠를 판에 적힌 판정으로 딴다(#281)
    PICK = 'pick'
    # 지금 장소에 닿은 길의 문을 판에 적힌 판정으로 부순다(#281)
    FORCE = 'force'
    # 지금 장소에 닿은 길의 부서진 문을 판에 적힌 판정으로 고친다(#281)
    REPAIR = 'repair'
    # 지금 장소에 닿은 길의 문의 자물쇠를 가진 자물쇠 물건으로 바꿔 단다. 옛 열쇠로는 더 열지 못한다(#281)
    REPLACE = 'replace'


class DoorDevice(enum.StrEnum):
    """문을 잠그는 장치(#281). 잠그기와 열기가 무엇으로 하는지다."""

    # 자물쇠. 그 열쇠를 지닌 사람이 길의 어느 끝에서든 잠그고 연다
    LOCK = 'lock'
    # 빗장. 빗장 쪽에 선 사람이 열쇠 없이 걸고 푼다
    BAR = 'bar'


class RestLength(enum.StrEnum):
    """휴식의 길이. 규칙의 Rest.short, Rest.long 에 맞춘다."""

    SHORT = 'short'
    LONG = 'long'


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
    # recover 가 있는데 target 도 npc 도 비우면 자기 자신이다(app/rounds/acceptance.py 가 채운다)
    target: uuid.UUID | None = None

    # 성공의 타격. 성공하면 대상 NPC 가 이 등급만큼 피해를 입는다. 규칙의 Magnitude.key 다
    harm: Key | None = None
    # 대상 NPC. 판의 로어북 인물 항목의 id 다. 이번 장면에 나온 인물만 고를 수 있다(app/rounds/cast.py).
    # 엔진은 이 값을 읽지 않는다
    npc: uuid.UUID | None = None
    # 대상 몬스터. 테이블의 몬스터 한 마리의 id 다(table_monsters.id). 자기가 선 장소의 마리만 고를 수 있다
    # (app/rounds/monster_scene.py). 타격에만 쓴다. 엔진은 이 값을 읽지 않는다
    monster: uuid.UUID | None = None
    # 타격이 죽이려는 것인가. 아니면 제압이다. HP 가 0 이 되면 제압은 쓰러뜨리고, 죽이려는 것은 죽인다
    lethal: bool = False
    # 노려 치기. 노릴 부상의 이름표(규칙의 Injury.key)다. 판정이 어려워지고, 성공하면 그 부상을 입힌다.
    # 그 타격에서는 부상 표를 굴리지 않는다
    aim: Key | None = None
    # 타격에 쓰는 무기(#276). 판의 물건 항목의 id 다. 행동하는 캐릭터가 착용한 것이어야 한다(app/rounds/acceptance.py).
    # 엔진은 이 값을 읽지 않는다. 공격 보정은 부른 쪽이 넘긴다
    weapon: uuid.UUID | None = None
    # 노릴 부위(#276). 규칙의 장비의 칸이다. 노려 치기와 같은 대가를 치른다. 비우면 맞은 부위를 서버가 굴린다
    strike: Key | None = None

    @model_validator(mode='after')
    def require_recover_for_target(self) -> Self:
        """대상(앉은 사람)은 회복에만 쓴다. 회복이 없는데 대상만 있으면 무엇을 하려는지 알 수 없다."""
        if self.target is not None and self.recover is None:
            raise ValueError('target 은 recover 와 함께 적습니다.')
        return self

    @model_validator(mode='after')
    def require_one_target(self) -> Self:
        """대상은 하나다. 앉은 사람, NPC, 몬스터 중 둘 이상을 함께 적지 않는다."""
        if self.target is not None and self.npc is not None:
            raise ValueError('target 과 npc 는 함께 적지 않습니다.')
        if self.monster is not None and (self.target is not None or self.npc is not None):
            raise ValueError('monster 는 target 이나 npc 와 함께 적지 않습니다.')
        return self

    @model_validator(mode='after')
    def require_harm_for_monster(self) -> Self:
        """
        몬스터에게 하는 일은 타격뿐이다. 회복과 노려 치기는 몬스터에게 하지 않는다.

        몬스터는 부상을 입지 않는다(부상은 앉은 사람과 NPC 의 것이다). 노릴 부상이 없다.
        """
        if self.monster is None:
            return self
        if self.harm is None:
            raise ValueError('monster 는 harm 과 함께 적습니다.')
        if self.aim is not None:
            raise ValueError('monster 에게는 aim 을 적지 않습니다.')
        return self

    @model_validator(mode='after')
    def require_npc_for_harm(self) -> Self:
        """
        타격과 NPC 는 함께 있다. 타격에는 맞을 NPC 가 있어야 하고, NPC 에게는 무엇을 할지가 있어야 한다.

        NPC 에게 하는 일은 타격이나 회복이다. 둘을 함께 붙이지 않는다. 성공하면 둘 중 하나만 일어날 수 있다.
        죽이려는지는 타격에만 뜻이 있다.
        """
        if self.harm is not None and self.npc is None and self.monster is None:
            raise ValueError('harm 은 npc 나 monster 와 함께 적습니다.')
        if self.npc is not None and self.harm is None and self.recover is None:
            raise ValueError('npc 는 harm 이나 recover 와 함께 적습니다.')
        if self.harm is not None and self.recover is not None:
            raise ValueError('harm 과 recover 는 함께 적지 않습니다.')
        if self.lethal and self.harm is None:
            raise ValueError('lethal 은 harm 과 함께 적습니다.')
        if self.aim is not None and self.harm is None:
            raise ValueError('aim 은 harm 과 함께 적습니다.')
        return self

    @model_validator(mode='after')
    def require_harm_for_weapon(self) -> Self:
        """
        무기와 노릴 부위는 타격에만 쓴다(#276). 부상을 노리면서 부위도 노리지 않는다. 노려 치기는 하나다.
        """
        if self.weapon is not None and self.harm is None:
            raise ValueError('weapon 은 harm 과 함께 적습니다.')
        if self.strike is not None and self.harm is None:
            raise ValueError('strike 는 harm 과 함께 적습니다.')
        if self.strike is not None and self.aim is not None:
            raise ValueError('strike 와 aim 은 함께 적지 않습니다.')
        return self


class TreatAction(BaseModel):
    """
    치료하는 행동. 대상이 입은 오래 가는 부상 하나를 치료한다.

    능력과 난이도는 받지 않는다. 규칙의 치료 능력과 그 부상의 치료 난이도로 판정한다.
    대상은 앉은 사람(target)이나 이번 장면의 NPC(npc) 중 하나다.
    둘 다 비우면 자기 자신이다(app/rounds/acceptance.py 가 채운다).
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.TREAT]
    # 치료할 부상의 이름표. 규칙의 Injury.key 다
    injury: Key
    # 치료받는 사람. 테이블에 앉은 사람이다. 엔진은 이 값을 읽지 않는다
    target: uuid.UUID | None = None
    # 치료받는 NPC. 판의 로어북 인물 항목의 id 다. 엔진은 이 값을 읽지 않는다
    npc: uuid.UUID | None = None

    @model_validator(mode='after')
    def require_one_patient(self) -> Self:
        """치료받는 쪽은 하나다. 앉은 사람과 NPC 를 함께 적지 않는다."""
        if self.target is not None and self.npc is not None:
            raise ValueError('target 과 npc 는 함께 적지 않습니다.')
        return self


# 지목할 때 짚는 이름의 길이
NAME_GUESS_MAX_LENGTH = 50


class NameAction(BaseModel):
    """
    지목하는 행동. 인물의 진짜 이름을 짚는다.

    npc 를 적으면 "이번 장면의 이 인물의 이름은 이것이다"다. 비우면 "이런 이름의 인물이 있다"다.
    장면에 없는 인물도 이름으로 짚을 수 있다. 맞으면 그 인물이 진짜 이름으로 불리기 시작한다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.NAME]
    # 짚은 이름. 앞뒤 공백을 뗀다
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_GUESS_MAX_LENGTH)]
    # 이름을 짚는 대상. 이번 장면에 나온 인물의 id 다. 엔진은 이 값을 읽지 않는다
    npc: uuid.UUID | None = None


# 한 번에 건넬 수 있는 개수. 한 가지를 가질 수 있는 개수와 같다(app/assets/models.py 의 ITEM_STACK_MAX)
GIVE_MAX_COUNT = 99


class UseAction(BaseModel):
    """
    물건을 쓰는 행동. 가진 소모품 하나를 쓴다(app/rounds/item_actions.py).

    item 은 판의 로어북 물건 항목의 id 다. 소모품이어야 한다. 엔진은 이 값을 읽지 않는다. 어떤 물건인지는 판이 안다.
    회복하는 소모품이면 대상(target)이 회복한다. 비우면 자기 자신이다(app/rounds/acceptance.py 가 채운다).
    회복하지 않는 소모품(연막탄 같은 것)은 대상이 없다. 쓰고 없어진다. 무엇이 일어나는지는 서술이 맡는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.USE]
    item: uuid.UUID
    # 회복받는 사람. 테이블에 앉은 사람이다
    target: uuid.UUID | None = None


class GiveAction(BaseModel):
    """물건을 건네는 행동. 가진 물건 count 개를 앉은 다른 사람(target)에게 건넨다(app/rounds/item_actions.py)."""

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.GIVE]
    item: uuid.UUID
    count: int = Field(default=1, ge=1, le=GIVE_MAX_COUNT)
    # 받는 사람. 테이블에 앉은 다른 사람이다
    target: uuid.UUID


class MoveAction(BaseModel):
    """
    맵에서 한 칸 가는 행동. 지금 서 있는 장소에서 아는 길로 이어진 장소(place)로 간다(app/rounds/map_actions.py).

    place 는 판의 로어북 장소 항목의 id 다. 엔진은 이 값을 읽지 않는다. 어디와 이어져 있는지는 판이 안다.
    한 라운드에 한 칸이다. 한 사람의 선언에는 행동이 하나다.
    carry 는 함께 업고 갈 쓰러진 동료(앉은 사람의 user_id)다. 한 사람이 한 명을 업는다(#367).
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.MOVE]
    place: uuid.UUID
    carry: uuid.UUID | None = None


class SearchAction(BaseModel):
    """
    지금 서 있는 장소에서 숨긴 길과 숨긴 물건을 찾는 행동(app/rounds/map_actions.py). 받는 값이 없다.

    무엇으로 굴리는지(능력과 난이도)는 길과 물건마다 판에 적혀 있다. 플레이어는 숨긴 것이 있는지조차 모른다.
    찾은 물건은 찾은 사람이 바로 갖는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.SEARCH]


class RestAction(BaseModel):
    """
    쉬는 행동(app/rounds/rests.py). 얼마나 쉬는지(length)만 받는다. 시간과 회복량은 규칙이 정한다.

    쉬는 라운드는 적어도 그 휴식의 시간만큼 이어진다. 그동안 다치면 휴식이 깨져 회복하지 않는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.REST]
    length: RestLength


# 기다리기로 부를 수 있는 가장 긴 시간(분). 일주일. 시계의 걸음의 상한(app/assets/models.py 의 ROUND_MAX_MINUTES)과 같다
WAIT_MAX_MINUTES = 7 * 24 * 60


class WaitAction(BaseModel):
    """
    시간을 건너뛰는 행동(app/rounds/waits.py). 얼마나 기다리는지(minutes, 1분~일주일)만 받는다.

    앉은 사람이 모두 기다리고 아무도 맞지 않았으면 다음 라운드가 적어도 가장 짧게 부른 시간만큼 뒤에 열린다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.WAIT]
    minutes: int = Field(ge=1, le=WAIT_MAX_MINUTES)


class TakeAction(BaseModel):
    """
    지금 서 있는 장소에 보이게 놓인 물건(item) count 개를 줍는 행동(app/rounds/place_item_actions.py).

    item 은 판의 로어북 물건 항목의 id 다. 판정이 없다. 남은 것보다 많이 부르면 남은 만큼, 한 가지의 상한까지 줍는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.TAKE]
    item: uuid.UUID
    count: int = Field(default=1, ge=1, le=GIVE_MAX_COUNT)


class PutDownAction(BaseModel):
    """
    가진 물건(item) count 개를 지금 서 있는 장소에 내려놓는 행동(app/rounds/place_item_actions.py).

    판정이 없다. 내려놓은 물건은 그 장소에 보이게 놓인 물건이 되어 누구나 줍기(take)로 가져간다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.PUT_DOWN]
    item: uuid.UUID
    count: int = Field(default=1, ge=1, le=GIVE_MAX_COUNT)


class StealAction(BaseModel):
    """
    같은 장소의 몬스터 한 마리(monster)나 이번 장면의 인물(npc)이 지닌 물건 하나(item)를 훔치는 행동
    (app/rounds/steals.py). monster 와 npc 중 하나만 적는다.

    능력과 난이도는 받지 않는다. 규칙(Ruleset.steal)이 정하고, 물건과 대상에 따라 목표값이 오르내린다.
    성공하면 그 줄을 통째로 갖는다. 들키면 몬스터는 이번 라운드의 차례에 도둑을 노린다.
    NPC 는 적대가 되고, 그 인물의 시트가 정했으면(on_caught: fight) 싸움도 붙는다(#457).
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.STEAL]
    # 테이블의 몬스터 한 마리의 id 다(table_monsters.id). 자기가 선 장소의 마리만 고를 수 있다
    monster: uuid.UUID | None = None
    # 판의 로어북 인물 항목의 id 다. 이번 장면의 죽지 않은 인물만 고를 수 있다(app/rounds/cast.py)
    npc: uuid.UUID | None = None
    # 그 대상이 지닌 물건의 항목 id 다. 장면의 인물이나 몬스터 목록의 items 에서 고른다
    item: uuid.UUID

    @model_validator(mode='after')
    def require_one_victim(self) -> Self:
        """훔칠 대상은 하나다. monster 와 npc 중 하나만 적는다."""
        if (self.monster is None) == (self.npc is None):
            raise ValueError('monster 와 npc 중 하나만 적습니다.')
        return self


class LootAction(BaseModel):
    """
    쓰러졌거나 죽은 대상이 지닌 물건 하나(item)를 가져가는 행동(app/rounds/loots.py, #475).

    대상은 같은 장소의 몬스터 한 마리(monster)나 이번 장면의 인물(npc)이다. 둘 중 하나만 적는다.
    판정이 없다. 그 줄을 통째로 갖는다. 살아 있는(쓰러지지 않은) 대상에게서는 가져가지 못한다. 그때는 훔치기다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.LOOT]
    # 테이블의 몬스터 한 마리의 id 다(table_monsters.id). 자기가 선 장소의 마리만 고를 수 있다. 죽었어도 된다
    monster: uuid.UUID | None = None
    # 판의 로어북 인물 항목의 id 다. 이번 장면의 인물만 고를 수 있다. 죽었어도 된다
    npc: uuid.UUID | None = None
    # 그 대상이 지닌 물건의 항목 id 다. 장면의 인물이나 몬스터 목록의 items 에서 고른다
    item: uuid.UUID

    @model_validator(mode='after')
    def require_one_victim(self) -> Self:
        """가져올 대상은 하나다. monster 와 npc 중 하나만 적는다."""
        if (self.monster is None) == (self.npc is None):
            raise ValueError('monster 와 npc 중 하나만 적습니다.')
        return self


class BuyAction(BaseModel):
    """
    이번 장면의 상인(npc)에게서 물건(item) count 개를 사는 행동(app/rounds/trades.py, #278).

    판정이 없다. 값은 판의 물건의 값 × 개수다. 상인의 소지품에 그만큼 있어야 하고(재고), 돈이 모자라면 사지 못한다.
    다 사거나 하나도 사지 않는다. 사려던 것보다 적게 사서 돈이 엉뚱하게 남는 일을 만들지 않는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.BUY]
    # 판의 로어북 인물 항목의 id 다. 이번 장면의 상인만 고를 수 있다(app/rounds/cast.py)
    npc: uuid.UUID
    # 판의 로어북 물건 항목의 id 다. 장면의 인물 목록의 items 에서 고른다
    item: uuid.UUID
    count: int = Field(default=1, ge=1, le=GIVE_MAX_COUNT)


class SellAction(BaseModel):
    """
    가진 물건(item) count 개를 이번 장면의 상인(npc)에게 파는 행동(app/rounds/trades.py, #278).

    판정이 없다. 받는 돈은 물건 하나의 값에 화폐의 백분율을 곱해 내림한 것 × 개수다.
    판 물건은 상인의 재고가 되지 않는다.
    다 팔거나 하나도 팔지 않는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.SELL]
    npc: uuid.UUID
    item: uuid.UUID
    count: int = Field(default=1, ge=1, le=GIVE_MAX_COUNT)


# 한 번에 건넬 수 있는 돈. 한 캐릭터가 가질 수 있는 돈과 같다(app/assets/models.py 의 MONEY_MAX)
PAY_MAX_AMOUNT = 1_000_000


class PayAction(BaseModel):
    """가진 돈 amount 를 앉은 다른 사람(target)에게 건네는 행동(app/rounds/trades.py, #278). 판정이 없다."""

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.PAY]
    # 받는 사람. 테이블에 앉은 다른 사람이다
    target: uuid.UUID
    amount: int = Field(ge=1, le=PAY_MAX_AMOUNT)


class LockAction(BaseModel):
    """
    지금 서 있는 장소에 닿은 길(place 로 이어진 길)의 문을 잠그는 행동(#281, app/rounds/door_actions.py).

    device 는 자물쇠(lock)인지 빗장(bar)인지다. 그 길에 하나만 있으면 비워도 된다. 둘 다 있으면 적어야 한다.
    자물쇠는 그 열쇠를 지녀야 잠그고, 빗장은 빗장 쪽에 서 있어야 건다. 부서진 문은 잠그지 못한다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.LOCK]
    place: uuid.UUID
    device: DoorDevice | None = None


class UnlockAction(BaseModel):
    """
    지금 서 있는 장소에 닿은 길의 문을 여는 행동(#281). 지나가지 않고 열기만 한다. device 는 잠그기와 같다.

    자물쇠는 그 열쇠를 지녀야 열고, 빗장은 빗장 쪽에 서 있어야 푼다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.UNLOCK]
    place: uuid.UUID
    device: DoorDevice | None = None


class PickAction(BaseModel):
    """
    지금 서 있는 장소에 닿은 길의 잠긴 자물쇠를 따는 행동(#281). 판에 적힌 따는 판정(능력, 난이도)으로 굴린다.

    판에 도구를 적었으면 그 물건을 지녀야 딴다. 성공하면 자물쇠가 열린다. 지나가지는 않는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.PICK]
    place: uuid.UUID


class ForceAction(BaseModel):
    """
    지금 서 있는 장소에 닿은 길의 문을 부수는 행동(#281). 판에 적힌 부수는 판정(능력, 난이도)으로 굴린다.

    성공하면 자물쇠와 빗장이 부서져 열린다. 부서진 문은 다시 잠그지 못한다. 지나가지는 않는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.FORCE]
    place: uuid.UUID


class RepairAction(BaseModel):
    """
    지금 서 있는 장소에 닿은 길의 부서진 문을 고치는 행동(#281). 판에 적힌 고치는 판정(능력, 난이도)으로 굴린다.

    판에 도구를 적었으면 그 물건을 지녀야 고친다. 성공하면 문이 고쳐져 다시 잠글 수 있다. 고친 문은 열린 채다.
    지나가지는 않는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.REPAIR]
    place: uuid.UUID


class ReplaceAction(BaseModel):
    """
    지금 서 있는 장소에 닿은 길의 문의 자물쇠를 바꿔 다는 행동(#281). 굴리지 않는다.

    item 은 지닌 자물쇠 물건(판에 자물쇠를 적은 물건 항목)이다. 판에 자물쇠가 있던 문에만 단다.
    부서진 문은 고친 뒤에, 잠긴 자물쇠는 연 뒤에 바꾼다. 단 자물쇠는 열린 채이고, 그 자물쇠 물건의 열쇠로만 잠그고 연다.
    자물쇠 물건은 소지품에서 하나 없어진다. 한 테이블에서 자물쇠 물건 하나는 한 번만 단다. 지나가지는 않는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.REPLACE]
    place: uuid.UUID
    item: uuid.UUID


# 문을 다루는 행동들(#281). 같은 곳에서 받고 판정한다(app/rounds/door_actions.py)
DoorAction = LockAction | UnlockAction | PickAction | ForceAction | RepairAction | ReplaceAction


# 행동의 모양들. 받은 행동을 종류로 가르는 함수들이 이것을 받는다
class CoverAction(BaseModel):
    """
    지금 서 있는 장소의 숨을 곳에 엄폐하는 행동(app/rounds/covers.py, #276 의 커버 세이브). 받는 값이 없다.

    그 라운드 동안 그 장소의 커버로 커버 세이브를 받는다. 차례를 기다리지 않는다. 숨는 것은 공격에 앞선다.
    그 라운드의 행동을 쓰므로 공격하지 못한다. 그것이 대가다.
    세이브 방식의 룰북에서, 커버가 있는 장소에 서 있을 때만 받는다. 서술이 "벽 뒤에 숨었다"고 써도 엄폐가 아니다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[ActionKind.COVER]


AnyAction = (
    CheckAction
    | TreatAction
    | NameAction
    | UseAction
    | GiveAction
    | MoveAction
    | SearchAction
    | RestAction
    | TakeAction
    | PutDownAction
    | StealAction
    | LootAction
    | WaitAction
    | BuyAction
    | SellAction
    | PayAction
    | CoverAction
    | LockAction
    | UnlockAction
    | PickAction
    | ForceAction
    | RepairAction
    | ReplaceAction
)

# 선언에 붙는 행동. kind 로 종류를 가른다
Action = Annotated[AnyAction, Field(discriminator='kind')]

# 저장된 행동(JSON)을 읽는 법. 우리가 쓴 문서다. 모양이 틀렸으면 버그다
ACTION = TypeAdapter(Action)


def read_action(data: dict) -> AnyAction:
    """선언에 저장된 행동을 읽는다. 모양이 틀리면 ValidationError."""
    return ACTION.validate_python(data)


def find_treat_fault(ruleset: Ruleset, action: TreatAction) -> str | None:
    """치료가 이 규칙에 맞지 않으면 틀린 칸의 이름(injury)을 돌려준다. 맞으면 None. 치료할 수 있는 부상이어야 한다."""
    if treatable(ruleset, action.injury) is None:
        return 'injury'
    return None


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
    if action.strike is not None and not armor.can_strike(ruleset, action.strike):
        return 'strike'
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

    부상을 노리든(aim) 부위를 노리든(strike, #276) 같은 대가다.
    받을 때 노릴 수 있는지 본 행동(find_fault)에만 쓴다.
    """
    if (action.aim is None and action.strike is None) or ruleset.called_shot is None:
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
    ruleset: Ruleset,
    action: CheckAction,
    abilities: dict[str, int],
    dice: Dice,
    hindrance: Hindrance,
    bonus: int = 0,
    raise_by: int = 0,
) -> HinderedCheck:
    """
    부상을 입은 캐릭터가 행동을 한다. 판정을 한 번 하고 그 결과를 돌려준다.

    hindrance 는 그 캐릭터의 부상이 이 행동의 능력에 주는 것이다(app/engine/injury.py 의 hindrance_of).
    노려 치면 규칙이 정한 만큼 어려워진다. 목표값이 오르거나(판정의 target 이 오른 값이다), 불리하다.
    bonus 는 무기의 공격 보정이다. 보정에 더한다. raise_by 는 맞은 부위의 방어가 목표값을 올리는 양이다(#276).

    받을 때 규칙에 맞는지 본 행동(find_fault, settle)과, 같은 규칙으로 검사한 시트에만 쓴다.
    그래서 여기서는 능력과 난이도가 있는지 다시 따지지 않는다.
    """
    difficulty = find_difficulty(ruleset, action.difficulty)
    aim_raise, aim_disadvantage = called_shot_terms(ruleset, action)
    if aim_raise or raise_by:
        difficulty = difficulty.model_copy(update={'target': difficulty.target + aim_raise + raise_by})
    score = abilities[action.ability]
    return resolve_hindered(
        ruleset, score, difficulty, dice, hindrance, forced_disadvantage=aim_disadvantage, bonus=bonus
    )


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
