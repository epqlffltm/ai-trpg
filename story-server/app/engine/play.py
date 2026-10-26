# story-server/app/engine/play.py

"""
사용자의 행동 하나를 끝까지 판정한다(docs/architecture/story.md 의 "시각", "이벤트", "고백과 엔딩"). 순수 함수다.

행동 하나의 차례.
  1. 기다리던 선택지가 있고 이 행동이 그 선택지를 고르는 것이 아니면, 선택지는 사라진다(효과 없이)
  2. 행동을 반영한다: 이동, 시간 보내기, 하루 마치기, 선택지 고르기, 고백, 건네기
  3. 고백이 엔딩을 봤으면 거기서 끝이다
  4. 시각이 흐른 행동이면 기한을 본다. 지났으면 기한의 엔딩을 보고 끝이다
  5. 열 수 있는 이벤트를 하나 연다. 그 이벤트로 시작되는 엔딩이 있으면 본다

할 수 없는 행동은 각 모듈의 예외로 올라간다(CannotMove, ChoiceRefused, ConfessionRefused, GiftRefused).
엔딩을 본 뒤(후일담)에도 이벤트는 열리지만 엔딩과 기한은 다시 일어나지 않는다(app/engine/endings.py 의 pick_ending).
행동의 글(모델에 보내는 문장)과 계정의 기록은 이 모듈 밖의 일이다(app/turns/).
"""

from dataclasses import dataclass, replace

from app.engine import actions, events
from app.engine.confession import confess
from app.engine.endings import deadline_ending, event_ending, reach_ending
from app.engine.gifts import give
from app.engine.scene import scene_cast
from app.engine.state import StoryState
from app.engine.world import Choice, Ending, Event, World


@dataclass(frozen=True)
class Move:
    """그 장소로 옮긴다."""

    place: str


@dataclass(frozen=True)
class PassTime:
    """다음 시간대로."""


@dataclass(frozen=True)
class EndDay:
    """다음 날의 첫 시간대로."""


@dataclass(frozen=True)
class Choose:
    """기다리는 이벤트의 선택지 하나를 고른다."""

    choice: str


@dataclass(frozen=True)
class Confess:
    """장면에 있는 인물 하나에게 고백한다."""

    cast: str


@dataclass(frozen=True)
class Give:
    """장면에 있는 인물 하나에게 가진 물건 하나를 건넨다."""

    cast: str
    item: str


Action = Move | PassTime | EndDay | Choose | Confess | Give

# 시각이 흐르는 행동. 이것들 뒤에만 기한을 본다
TIME_FLOWS = (Move, PassTime, EndDay)


@dataclass(frozen=True)
class Played:
    """
    행동 하나를 판정한 결과. state 는 행동 뒤의 상태다.
    choice 는 고른 선택지, accepted 는 고백이 받아들여졌는가(고백이 아니면 None)다.
    affection_change 는 건네기로 호감도가 바뀐 양이다(건네기가 아니면 None, 맞는 규칙이 없으면 0).
    event 는 이 행동 뒤에 열린 이벤트, ending 은 이 행동으로 본 엔딩이다(없으면 None).
    """

    state: StoryState
    choice: Choice | None = None
    accepted: bool | None = None
    affection_change: int | None = None
    event: Event | None = None
    ending: Ending | None = None


def act(world: World, state: StoryState, action: Action) -> Played:
    """행동 자체를 반영한다(위 차례의 1~2). 고백의 엔딩까지만 본다."""
    match action:
        case Move(place=place):
            return Played(actions.move_to(world, events.drop_choice(state), place))
        case PassTime():
            return Played(actions.pass_time(world, events.drop_choice(state)))
        case EndDay():
            return Played(actions.end_day(world, events.drop_choice(state)))
        case Choose(choice=choice_id):
            chosen, choice = events.choose(world, state, choice_id)
            return Played(chosen, choice=choice)
        case Confess(cast=cast_id):
            before = events.drop_choice(state)
            outcome = confess(world, before, cast_id, scene_cast(world, before))
            return Played(outcome.state, accepted=outcome.succeeded, ending=outcome.ending)
        case Give(cast=cast_id, item=item):
            before = events.drop_choice(state)
            given = give(world, before, cast_id, item, scene_cast(world, before))
            return Played(given.state, affection_change=given.change)
    raise TypeError(f'모르는 행동: {action!r}')


def after_deadline(world: World, played: Played) -> Played:
    """기한이 지났으면 기한의 엔딩을 본 결과. 아니면 그대로다."""
    ending = deadline_ending(world, played.state)
    if ending is None:
        return played
    return replace(played, state=reach_ending(played.state, ending), ending=ending)


def after_event(world: World, played: Played) -> Played:
    """열 수 있는 이벤트를 하나 연 결과. 그 이벤트로 시작되는 엔딩이 있으면 본다."""
    opened, event = events.open_next_event(world, played.state)
    if event is None:
        return played
    ending = event_ending(world, opened, event.id)
    if ending is None:
        return replace(played, state=opened, event=event)
    return replace(played, state=reach_ending(opened, ending), event=event, ending=ending)


def play(world: World, state: StoryState, action: Action) -> Played:
    """행동 하나를 끝까지 판정한다(위 차례의 1~5). 할 수 없는 행동이면 그 모듈의 예외다."""
    played = act(world, state, action)
    if played.ending is not None:
        return played
    if isinstance(action, TIME_FLOWS):
        played = after_deadline(world, played)
        if played.ending is not None:
            return played
    return after_event(world, played)
