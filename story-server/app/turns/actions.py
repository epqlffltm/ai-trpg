# story-server/app/turns/actions.py

"""
행동의 요청을 엔진의 행동으로 바꾸고, 판정하고, 행동 말의 글을 만든다. DB 도 모델도 모른다.

  - 판정은 엔진이 한다(app/engine/play.py). 할 수 없는 행동이면 ActionRefusedError 이고 code 가 까닭이다.
    아무것도 저장하지 않는다(app/turns/service.py 의 begin_action)
  - 행동 말의 글은 사람이 한 행동과 엔진이 정한 결과(고백을 받아들였는가)를 적는다. 모델에 [행동] 을 붙여 간다.
    모델은 그 결과를 바꾸지 못하고 그에 맞는 반응만 쓴다. 열린 이벤트와 본 엔딩은 장면 지시로 간다(app/turns/scenes.py)

    거절의 code
      cannot_move                         지금 장소이거나 길로 바로 이어지지 않은 장소다
      no_choice                           고르기를 기다리는 이벤트가 없거나 그런 선택지가 없다
      over, not_in_scene,                 고백을 받지 않는다(이미 엔딩을 봤다, 장면에 없는 인물이다,
      not_confessable, cooling_down       고백할 수 없는 인물이다, 다시 고백할 시각이 아직이다)
"""

from app.engine import play
from app.engine.actions import CannotMove
from app.engine.clock import day_of, slot_of
from app.engine.confession import ConfessionRefused
from app.engine.events import ChoiceRefused
from app.engine.play import Played
from app.engine.state import StoryState
from app.engine.world import World
from app.turns.briefing import Briefing
from app.turns.schemas import ActionCreate, ChooseAction, ConfessAction, EndDayAction, MoveAction, PassTimeAction

CANNOT_MOVE = 'cannot_move'
NO_CHOICE = 'no_choice'


class ActionRefusedError(Exception):
    """할 수 없는 행동이다(422). code 가 까닭이다."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def to_engine(data: ActionCreate) -> play.Action:
    """요청의 행동을 엔진의 행동으로."""
    match data:
        case MoveAction(place=place):
            return play.Move(place)
        case PassTimeAction():
            return play.PassTime()
        case EndDayAction():
            return play.EndDay()
        case ChooseAction(choice=choice):
            return play.Choose(choice)
        case ConfessAction(cast=cast):
            return play.Confess(cast)
    raise TypeError(f'모르는 행동: {data!r}')


def perform(world: World, state: StoryState, action: play.Action) -> Played:
    """행동을 끝까지 판정한다. 할 수 없으면 ActionRefusedError."""
    try:
        return play.play(world, state, action)
    except CannotMove as error:
        raise ActionRefusedError(CANNOT_MOVE) from error
    except ChoiceRefused as error:
        raise ActionRefusedError(NO_CHOICE) from error
    except ConfessionRefused as error:
        raise ActionRefusedError(error.reason.value) from error


def place_name(briefing: Briefing, place_id: str) -> str:
    """장소의 이름. 판에 이름이 없으면 id 그대로다."""
    place = briefing.place(place_id)
    return place.name if place is not None and place.name else place_id


def clock_words(briefing: Briefing, world: World, state: StoryState) -> str:
    """지금의 날과 시간대('2일째 아침')."""
    return f'{day_of(state.minutes)}일째 {briefing.slot_name(slot_of(world, state.minutes))}'


def action_text(briefing: Briefing, world: World, action: play.Action, played: Played) -> str:
    """행동 말의 글. 사람이 한 것과 엔진이 정한 결과다."""
    match action:
        case play.Move(place=place):
            return f'{place_name(briefing, place)}(으)로 갔다. 지금은 {clock_words(briefing, world, played.state)}.'
        case play.PassTime():
            return f'시간을 보냈다. 지금은 {clock_words(briefing, world, played.state)}.'
        case play.EndDay():
            return f'하루를 마쳤다. 지금은 {clock_words(briefing, world, played.state)}.'
        case play.Choose():
            return f'고른 것: {played.choice.text}' if played.choice is not None else '골랐다.'
        case play.Confess(cast=cast):
            answer = '받아들였다' if played.accepted else '받아들이지 않았다'
            return f'{briefing.cast_name(cast)}에게 고백했다. {briefing.cast_name(cast)}은(는) 고백을 {answer}.'
    raise TypeError(f'모르는 행동: {action!r}')
