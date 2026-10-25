# story-server/app/engine/events.py

"""
이벤트를 열고 선택지를 고른다(docs/architecture/story.md 의 "이벤트"). 판과 상태만 보는 순수 함수다.

흐름.
  1. 행동(이동, 시간, 건네기, 선택지, 고백) 뒤에 엔진이 열 수 있는 이벤트를 본다(open_next_event).
     조건이 맞는 것 가운데 판에 적은 차례로 하나만 연다. 되풀이가 아니면 한 번 열린 이벤트는 다시 열리지 않는다.
  2. 열리면 "본 이벤트"에 넣고 열릴 때의 효과를 반영한다. 선택지가 있으면 고르기를 기다린다(상태의 choosing)
  3. 사용자가 선택지를 고르면(choose) 그 효과를 반영하고 기다림을 끝낸다. 고르는 것도 행동이라 그 뒤에 다시 1 을 본다
  4. 선택지를 고르지 않고 말을 잇거나 다른 행동을 하면 선택지는 사라지고 효과는 없다(drop_choice)
행동 하나에 이벤트는 하나만 열린다. 열린 이벤트의 효과로 다른 이벤트의 조건이 맞아도 다음 행동 뒤에 연다.
이벤트가 열린 뒤의 장면(모델이 쓰는 글)과 일러스트를 계정에 남기는 것은 이 모듈 밖의 일이다.
"""

from dataclasses import replace

from app.engine.conditions import match_conditions
from app.engine.effects import apply_effects
from app.engine.state import StoryState
from app.engine.world import Choice, Event, World


class ChoiceRefused(Exception):
    """그 선택지를 고를 수 없다. 고르기를 기다리는 이벤트가 없거나, 그 이벤트에 그런 선택지가 없다."""


def can_open(event: Event, state: StoryState, world: World) -> bool:
    """그 이벤트가 지금 열릴 수 있나. 한 번만인데 이미 열렸으면 아니다. 그다음 조건을 본다."""
    if not event.repeat and event.id in state.seen:
        return False
    return match_conditions(event.when, state, world)


def next_event(world: World, state: StoryState) -> Event | None:
    """지금 열 이벤트. 열릴 수 있는 것 가운데 판의 차례로 첫 번째다. 없으면 None."""
    return next((event for event in world.events if can_open(event, state, world)), None)


def open_event(world: World, state: StoryState, event: Event) -> StoryState:
    """그 이벤트를 연 상태. 본 이벤트에 넣고, 열릴 때의 효과를 반영하고, 선택지가 있으면 고르기를 기다린다."""
    seen = replace(state, seen=state.seen | {event.id})
    opened = apply_effects(event.on_open, seen, world)
    return replace(opened, choosing=event.id if event.choices else None)


def open_next_event(world: World, state: StoryState) -> tuple[StoryState, Event | None]:
    """열 이벤트가 있으면 연 상태와 그 이벤트. 없으면 상태 그대로와 None."""
    event = next_event(world, state)
    if event is None:
        return state, None
    return open_event(world, state, event), event


def waiting_choice(world: World, state: StoryState, choice_id: str) -> Choice:
    """고르기를 기다리는 이벤트의 그 선택지. 기다리는 이벤트가 없거나 그런 선택지가 없으면 ChoiceRefused."""
    event = world.event(state.choosing or '')
    if event is None:
        raise ChoiceRefused
    choice = next((choice for choice in event.choices if choice.id == choice_id), None)
    if choice is None:
        raise ChoiceRefused
    return choice


def choose(world: World, state: StoryState, choice_id: str) -> tuple[StoryState, Choice]:
    """선택지를 고른 상태와 그 선택지. 그 효과를 반영하고 기다림을 끝낸다. 고를 수 없으면 ChoiceRefused."""
    choice = waiting_choice(world, state, choice_id)
    chosen = apply_effects(choice.effects, replace(state, choosing=None), world)
    return chosen, choice


def drop_choice(state: StoryState) -> StoryState:
    """선택지를 고르지 않고 넘어간 상태. 기다리던 선택지가 사라진다(효과는 없다)."""
    return replace(state, choosing=None)
