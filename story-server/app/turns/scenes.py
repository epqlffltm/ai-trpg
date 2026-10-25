# story-server/app/turns/scenes.py

"""
답을 쓰는 장면을 정한다. 장면의 인물과 모델에게 줄 장면 지시의 글이다. DB 도 모델도 모른다.

  - 엔딩을 본 행동의 답: 그 엔딩의 장면(이름과 장면 지시). 그 장면이 부르는 인물이 들어온다
  - 이벤트가 열린 행동의 답: 그 이벤트의 장면 지시. 그 장면이 부르는 인물이 들어온다
  - 그 밖(말, 아무것도 열리지 않은 행동): 장면 지시가 없다. 그 장소의 인물만이다
선택지를 기다리는 동안 말을 하면 선택지가 사라지므로(app/engine/events.py 의 drop_choice) 그 답에는 장면 지시가 없다.
"""

from dataclasses import dataclass

from app.engine.scene import scene_cast
from app.engine.state import StoryState
from app.engine.world import Ending, Event, Scene, World


@dataclass(frozen=True)
class Staging:
    """답을 쓰는 장면. cast 는 장면의 인물(인물의 id), direction 은 장면 지시의 글이다(없으면 빈 글)."""

    cast: tuple[str, ...]
    direction: str


def ending_direction(ending: Ending) -> str:
    """엔딩의 장면 지시. 엔딩의 이름을 앞에 적는다. 모델이 이야기를 맺는 장면임을 안다."""
    name = ending.name.strip() or ending.id
    body = ending.scene.text.strip()
    return f'엔딩 「{name}」에 닿았다. 이야기를 맺는 장면을 쓴다.' + (f'\n{body}' if body else '')


def chosen_scene(event: Event | None, ending: Ending | None) -> tuple[Scene | None, str]:
    """쓸 장면과 그 지시의 글. 엔딩이 이벤트보다 앞선다. 둘 다 없으면 (None, 빈 글)."""
    if ending is not None:
        return ending.scene, ending_direction(ending)
    if event is not None:
        return event.scene, event.scene.text.strip()
    return None, ''


def staging(world: World, state: StoryState, event: Event | None = None, ending: Ending | None = None) -> Staging:
    """state 에서 답을 쓰는 장면. 장면이 부르는 인물은 그 장소에 없어도 들어온다(app/engine/scene.py)."""
    scene, direction = chosen_scene(event, ending)
    called = scene.cast if scene is not None else ()
    return Staging(cast=tuple(scene_cast(world, state, called)), direction=direction)
