# game-server/app/rounds/schemas.py

"""
라운드 API 가 받는 입력과 내보내는 응답의 모양.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.engine.action import CheckAction
from app.engine.death import Fate
from app.engine.health import ChangeKind
from app.rounds.models import DECLARATION_MAX_LENGTH, RoundStatus
from app.tables.models import NpcStatus

# 선언의 글. 공백이 아닌 글자가 하나는 있어야 한다. 앞뒤 공백은 떼지 않는다
DeclarationContent = Annotated[str, StringConstraints(pattern=r'\S', max_length=DECLARATION_MAX_LENGTH)]


class DeclarationUpdate(BaseModel):
    """
    선언을 낼 때 받는 값. 다시 내면 앞의 것을 통째로 바꾼다. 행동을 빼고 다시 내면 행동도 없어진다.

    행동은 하나만 붙인다. 한 사람이 한 라운드에 주사위를 한 번 굴린다.
    행동이 없으면 판정이 없는 선언이다.
    """

    model_config = ConfigDict(extra='forbid')

    content: DeclarationContent
    action: CheckAction | None = None


class EffectOut(BaseModel):
    """판정의 결과로 HP 가 바뀐 것. 엔진이 정한 것이다."""

    # damage(피해) 또는 recovery(회복)
    kind: ChangeKind
    # 양의 등급. 규칙의 Magnitude.key 다
    magnitude: str
    # HP 가 바뀐 사람과 그 캐릭터. 피해는 행동한 사람, 회복은 행동의 대상이다
    user_id: uuid.UUID
    character_name: str
    # 주사위의 눈들과 그 합
    rolls: list[int]
    amount: int
    # 바뀌기 전과 뒤의 HP. 차이가 amount 보다 작을 수 있다. 0 이나 최대에 닿으면 거기서 멈춘다
    before: int
    after: int
    max_hp: int
    # 바뀐 뒤에 쓰러져 있는가(HP 0)
    downed: bool


class NpcEffectOut(BaseModel):
    """
    판정의 결과로 NPC 의 상태가 바뀐 것. 엔진이 정한 것이다.

    HP 의 숫자(바뀌기 전과 뒤, 최대)는 싣지 않는다. GM 만 안다. 주사위의 눈과 양, 바뀐 생사는 보인다.
    """

    # damage(피해) 또는 recovery(회복)
    kind: ChangeKind
    # 양의 등급. 규칙의 Magnitude.key 다
    magnitude: str
    # 바뀐 NPC. 이번 장면의 인물 목록의 id 와, 장면에서 부르는 이름
    entry_id: uuid.UUID
    name: str
    # 주사위의 눈들과 그 합
    rolls: list[int]
    amount: int
    # 죽이려는 타격이었는가
    lethal: bool
    # 바뀐 뒤의 생사
    status: NpcStatus


class CheckOutcome(BaseModel):
    """판정의 결과. 엔진이 정한 것이다(app/engine/check.py 의 Check). 받는 값이 아니라 내보내는 값이다."""

    # 주사위의 눈
    roll: int
    # 능력치의 점수에서 나온 보정
    modifier: int
    # 눈에 보정을 더한 값
    total: int
    # 난이도의 목표값. total 이 이 값 이상이면 성공이다
    target: int
    success: bool
    # 이 판정으로 HP 가 바뀌었으면 그 내용. 바뀌지 않았으면 None 이다
    effect: EffectOut | None = None
    # 이 판정으로 NPC 의 상태가 바뀌었으면 그 내용. 바뀌지 않았으면 None 이다. effect 와 함께 있지 않다
    npc_effect: NpcEffectOut | None = None


class DeclarationOut(BaseModel):
    """선언 하나."""

    user_id: uuid.UUID
    character_name: str
    # 선언의 글. 선언을 받는 동안에는 자기 것만 보인다. 남의 것은 None 이다.
    # 선언을 마감하면(닫는 중부터) 모두의 것이 보인다
    content: str | None
    # 선언에 붙인 행동. 글과 같이 가린다. 행동이 없는 선언이면 보이는 사람에게도 None 이다
    action: CheckAction | None
    # 행동의 결과. 선언을 마감할 때(닫는 중부터) 생긴다. 굴림은 공개라 모두에게 보인다.
    # 행동이 없는 선언과 아직 열려 있는 라운드의 선언은 None 이다
    outcome: CheckOutcome | None


class DeathSaveOut(BaseModel):
    """죽음의 굴림 한 번. 엔진이 굴린 것이다(app/engine/death.py 의 DeathSaveRoll)."""

    user_id: uuid.UUID
    character_name: str
    # 주사위의 눈과 넘어야 하는 값. 눈이 이 값 이상이면 성공이다. 능력치의 보정은 없다
    roll: int
    target: int
    success: bool
    # 이 굴림까지 센 성공과 실패
    successes: int
    failures: int
    # 이 굴림 뒤의 갈림길. dying(죽어 가는 중), stable(고비를 넘김), dead(죽음)
    fate: Fate


class ArrivalOut(BaseModel):
    """이 라운드에 새로 들어온 캐릭터 하나. 캐릭터가 죽은 플레이어가 들인 새 캐릭터다."""

    user_id: uuid.UUID
    character_name: str
    # 같은 플레이어의 죽은 캐릭터의 이름
    replaces: str


class RoundOut(BaseModel):
    """앉은 사람이 라운드를 볼 때의 값."""

    number: int
    # 이 라운드를 여는 장면. GM 의 서술이다
    scene: str
    # open: 선언을 받는 중. closing: 선언을 마감했고 GM 이 서술하는 중. closed: 끝났다
    status: RoundStatus
    declarations: list[DeclarationOut]
    # 이 라운드가 닫힐 때 굴린 죽음의 굴림들. 선언을 마감할 때(닫는 중부터) 생긴다. 굴린 것이 없으면 비어 있다
    death_saves: list[DeathSaveOut]
    # 이 라운드에 새로 들어온 캐릭터들. 들어온 순서다. 가리지 않는다. 누가 들어왔는지는 테이블에서도 보인다
    arrivals: list[ArrivalOut]
    # 선언을 내야 하는데 아직 내지 않은 사람들. 쓰러진 사람과 이 라운드에 새 캐릭터를 들인 사람은 들어가지 않는다.
    # 선언을 받는 중이 아니면 비어 있다
    waiting_for: list[uuid.UUID]
    created_at: datetime
    # 닫기 시작한 시각과 닫힌 시각. 아직이면 None 이다
    closing_at: datetime | None
    closed_at: datetime | None
    # 서술이 끝내 실패한 시각. 있으면 방장이 기다리지 않고 다시 맡길 수 있다. 다시 맡기면 비워진다
    narration_failed_at: datetime | None


class PersonOut(BaseModel):
    """이번 장면의 인물 하나. 행동으로 겨눌 수 있는 NPC 다(죽은 인물은 겨누지 못한다)."""

    # 행동의 npc 칸에 적는 값. 판의 로어북 인물 항목의 id 다
    id: uuid.UUID
    # 장면에서 부르는 이름. 장면에 나온 낱말이다
    name: str
    # 살아 있음, 쓰러짐, 죽음. HP 의 숫자는 싣지 않는다
    status: NpcStatus


class SceneCastOut(BaseModel):
    """
    가장 최근 라운드의 장면에 나온 인물들. 판의 인물 순서다.

    장면에 이름이나 호칭이 나온 인물만 들어간다. 로어북의 내용은 싣지 않는다.
    """

    # 어느 라운드의 장면인가
    round: int
    people: list[PersonOut]


class RoundPage(BaseModel):
    """라운드 목록의 한 쪽."""

    items: list[RoundOut]
    # 전체 개수. 다음 쪽이 있는지 알 수 있다
    total: int = Field(ge=0)
