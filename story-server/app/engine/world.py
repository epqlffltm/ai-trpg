# story-server/app/engine/world.py

"""
엔진이 읽는 판의 칸(asset-server 의 app/worlds/documents.py 의 WorldDocument 가운데 일부).

판은 asset 서버가 게시할 때 검사했다(없는 것을 가리키지 않는다, 칸의 모양이 맞다). 여기서는 엔진이 쓰는 칸만
읽는 모양으로 바꾼다. 모르는 칸은 버린다(extra='ignore'). 쓰는 칸이 늘면 그 칸을 여기에 더한다.
판의 형식 1 에는 이벤트가 없다. 그 판은 이벤트가 빈 것으로 읽는다.
시간대는 시작 시각이 이른 것부터 적혀 있다(asset 서버가 게시할 때 검사한다).
"""

import enum
import uuid
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from app.engine.effects import Effect


class ConditionKind(enum.StrEnum):
    """
    조건 하나가 무엇을 보는가. asset 서버의 ConditionKind 와 같은 값이다(docs/architecture/story.md 의 "조건").

      reach_place        target: 장소          사용자가 그 장소에 있다
      hold_item          target: 물건, count   그 물건을 count 개 이상 가졌다
      gave_item          target: 인물, value: 물건   그 인물에게 그 물건을 건넨 적이 있다
      affection_at_least target: 인물, value: 단계   그 인물의 호감도가 그 단계 이상이다
      affection_below    target: 인물, value: 단계   그 인물의 호감도가 그 단계보다 아래다
      day_at_least       count                 n일째 이상이다
      day_at_most        count                 n일째 이하다
      slot_is            target: 시간대        지금의 시간대가 그것이다
      accompanied        target: 인물          그 인물과 동행 중이다
      event_seen         target: 이벤트        그 이벤트가 열린 적이 있다
    """

    REACH_PLACE = 'reach_place'
    HOLD_ITEM = 'hold_item'
    GAVE_ITEM = 'gave_item'
    AFFECTION_AT_LEAST = 'affection_at_least'
    AFFECTION_BELOW = 'affection_below'
    DAY_AT_LEAST = 'day_at_least'
    DAY_AT_MOST = 'day_at_most'
    SLOT_IS = 'slot_is'
    ACCOMPANIED = 'accompanied'
    EVENT_SEEN = 'event_seen'


class Match(enum.StrEnum):
    """조건 목록을 맞추는 법. 모두, 또는 하나라도."""

    ALL = 'all'
    ANY = 'any'


class Part(BaseModel):
    """판의 칸을 읽는 모양의 공통. 모르는 칸은 버리고 읽은 뒤에는 바꾸지 않는다."""

    model_config = ConfigDict(extra='ignore', frozen=True)


class Condition(Part):
    """조건 하나. 쓰지 않는 칸은 비어 있다(count 는 1)."""

    kind: ConditionKind
    target: str | None = None
    value: str | None = None
    count: int = 1


class Conditions(Part):
    """조건 목록과 맞추는 법. 목록이 비면 늘 맞는다."""

    match: Match = Match.ALL
    items: tuple[Condition, ...] = ()


class Slot(Part):
    """시간대 하나. start_hour 부터 다음 시간대가 시작할 때까지다."""

    id: str
    name: str
    start_hour: int


class Path(Part):
    """두 장소를 잇는 길. 양쪽으로 다니고 minutes 분이 걸린다."""

    a: str
    b: str
    minutes: int


class ScheduleLine(Part):
    """일정의 줄 하나. 그 시간대에 when 이 맞으면 인물이 그 장소에 있다. 위의 줄부터 맞춰 본다."""

    slot: str
    place: str
    when: Conditions = Conditions()


class Stage(Part):
    """호감도의 단계 하나. at 이상이면 이 단계다."""

    name: str
    at: int


class Affection(Part):
    """인물의 호감도. 시작 값과 단계들."""

    start: int = 0
    stages: tuple[Stage, ...] = ()


class ConfessionFailure(enum.StrEnum):
    """고백에 실패하면 어떻게 되는가. 계속(호감도가 내려가고 정한 날 동안 다시 못 한다) 또는 실패 엔딩으로 끝."""

    CONTINUE = 'continue'
    END = 'end'


class Confession(Part):
    """인물에게 하는 고백. 호감도가 stage 이상이고 when 이 맞으면 성공이다. 실패하면 on_fail 대로 한다."""

    stage: str
    when: Conditions = Conditions()
    on_fail: ConfessionFailure = ConfessionFailure.CONTINUE
    fail_drop: int = 10
    cooldown_days: int = 1


class CastMember(Part):
    """인물 하나. home 이 비면 일정이나 이벤트로만 나온다. confession 이 비면 고백할 수 없는 인물이다."""

    id: str
    home: str | None = None
    schedule: tuple[ScheduleLine, ...] = ()
    affection: Affection = Affection()
    confession: Confession | None = None


class Scene(Part):
    """
    이벤트의 장면 지시. text 는 모델에게 주는 상황 설명, cast 는 장면에 불러들이는 인물이다.
    image_id 는 일러스트이고, collectible 이면 열릴 때 계정에 남는다(갤러리).
    """

    text: str = ''
    cast: tuple[str, ...] = ()
    image_id: uuid.UUID | None = None
    collectible: bool = False


class Choice(Part):
    """선택지 하나. 제작자가 적은 글과, 고르면 엔진이 반영하는 효과들이다."""

    id: str
    text: str
    effects: tuple[Effect, ...] = ()


class Event(Part):
    """
    이벤트 하나. 판의 차례가 여는 차례다. when 이 맞으면 열린다. repeat 이 아니면 한 번만 열린다.
    열리면 on_open 의 효과를 반영하고, choices 가 있으면 사용자가 하나를 고를 때까지 기다린다.
    """

    id: str
    name: str = ''
    when: Conditions = Conditions()
    repeat: bool = False
    scene: Scene = Scene()
    on_open: tuple[Effect, ...] = ()
    choices: tuple[Choice, ...] = ()


class EndingTrigger(enum.StrEnum):
    """엔딩의 판정이 무엇으로 시작되는가. 고백 성공·실패(target: 인물), 기한(target 없음), 이벤트(target: 이벤트)."""

    CONFESS_SUCCESS = 'confess_success'
    CONFESS_FAIL = 'confess_fail'
    DEADLINE = 'deadline'
    EVENT = 'event'


class Trigger(Part):
    """엔딩의 시작."""

    kind: EndingTrigger
    target: str | None = None


class Ending(Part):
    """엔딩 하나. 판의 차례가 맞춰 보는 차례다. unlock 이면 계정의 엔딩 기록에 남는다."""

    id: str
    name: str = ''
    trigger: Trigger
    when: Conditions = Conditions()
    scene: Scene = Scene()
    unlock: bool = True
    hint: str = ''


class AfterEnding(enum.StrEnum):
    """엔딩 뒤에 세션이 어떻게 되는가. 끝(읽기만) 또는 후일담."""

    END = 'end'
    EPILOGUE = 'epilogue'


class StartItem(Part):
    """사용자가 처음에 가진 물건과 그 수."""

    item: str
    count: int


class World(Part):
    """엔진이 읽는 판. 인물과 이벤트는 판에 적은 차례 그대로다."""

    slots: tuple[Slot, ...]
    start_slot: str
    # 기한(며칠째까지). 비어 있으면 기한이 없다
    deadline_days: int | None = None
    paths: tuple[Path, ...] = ()
    start_place: str
    start_items: tuple[StartItem, ...] = ()
    cast: tuple[CastMember, ...] = ()
    events: tuple[Event, ...] = ()
    # 판의 형식 2 까지는 엔딩이 없다
    endings: tuple[Ending, ...] = ()
    after_ending: AfterEnding = AfterEnding.END

    def member(self, cast_id: str) -> CastMember | None:
        """그 id 의 인물. 없으면 None."""
        return next((member for member in self.cast if member.id == cast_id), None)

    def slot(self, slot_id: str) -> Slot | None:
        """그 id 의 시간대. 없으면 None."""
        return next((slot for slot in self.slots if slot.id == slot_id), None)

    def event(self, event_id: str) -> Event | None:
        """그 id 의 이벤트. 없으면 None."""
        return next((event for event in self.events if event.id == event_id), None)

    def ending(self, ending_id: str) -> Ending | None:
        """그 id 의 엔딩. 없으면 None."""
        return next((ending for ending in self.endings if ending.id == ending_id), None)


def read_world(document: Mapping) -> World:
    """판의 문서(사본의 document)를 엔진이 읽는 모양으로 바꾼다."""
    return World.model_validate(document)
