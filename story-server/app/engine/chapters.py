# story-server/app/engine/chapters.py

"""
장을 넘긴다(docs/architecture/chapters.md). 판과 상태만 보는 순수 함수다.

  - 장이 있는 판은 첫 장에서 시작한다(app/engine/state.py 의 start_state). 장이 없는 판은 장이 없다(None)
  - 행동 하나를 끝까지 판정한 뒤 맨 끝에 다음 장의 조건을 본다. 맞으면 다음 장으로 넘어간다(advance_chapter)
  - 한 번에 한 장만, 앞으로만 넘어간다. 두 장의 조건이 함께 맞아도 다음 행동에서 또 넘어간다
  - 장이 바뀌어 새로 열린 장소와 이벤트는 다음 행동부터 본다(그 행동의 이벤트는 이미 판정했다)
열린 장소와 이벤트를 고르는 것은 판의 칸(app/engine/world.py 의 place_open, event_open)이 한다.
모델은 장을 바꾸지 못한다.
"""

from dataclasses import replace

from app.engine.conditions import match_conditions
from app.engine.state import StoryState
from app.engine.world import Chapter, World


def next_chapter(world: World, state: StoryState) -> Chapter | None:
    """지금 장 바로 뒤의 장. 장이 없는 판이거나 마지막 장이면 None."""
    if not world.chapters:
        return None
    following = world.reached_index(state.chapter) + 1
    return world.chapters[following] if following < len(world.chapters) else None


def advance_chapter(world: World, state: StoryState) -> tuple[StoryState, Chapter | None]:
    """다음 장의 조건이 맞으면 그 장으로 넘어간 상태와 그 장. 아니면 상태 그대로와 None."""
    chapter = next_chapter(world, state)
    if chapter is None or not match_conditions(chapter.when, state, world):
        return state, None
    return replace(state, chapter=chapter.id), chapter
