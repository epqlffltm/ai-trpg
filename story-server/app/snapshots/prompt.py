# story-server/app/snapshots/prompt.py

"""
장면 그림의 지시(#983). DB 도 모델도 모르는 순수 함수다.
chat 의 것(chat-server/app/snapshots/prompt.py)과 같은 규칙이다.

  - 세계관과 장면의 인물(이름, 나이, 성별, 소개의 글자)은 세션이 가져온 판의 사본에서,
    며칠째·시간대·장소는 엔진의 상태에서 온다. 모델이 글로 지어낸 상태(장소를 옮겼다)를 쓰지 않는다
  - 장면의 인물은 그 답에 적힌 인물(엔진이 정한 장면의 인물)이다
  - 일어나는 일은 그 답의 말 조각(과 그 답이 답한 사람의 말)에서 앞의 몇 글자만 쓴다
  - 맨 앞에 지킬 것을 둔다. 모든 등급에서 전체이용가로 그린다
"""

from collections.abc import Mapping, Sequence

from app.engine.clock import day_of, slot_of
from app.engine.state import StoryState
from app.engine.world import World
from app.turns.briefing import Briefing
from app.turns.prompt import plain_text

# 지킬 것. 모든 등급에서 같다
RULES = (
    '이야기의 한 장면을 그린 그림 한 장이다.',
    '전체이용가로 그린다. 노출, 성적인 묘사, 잔혹한 묘사를 넣지 않는다.',
    '글자, 말풍선, 서명, 워터마크를 넣지 않는다.',
)
# 소개에서 쓰는 글자 수(세계관, 인물마다)
WORLD_INTRO_CHARS = 200
MEMBER_INTRO_CHARS = 150
# 일어나는 일에서 쓰는 글자 수(답, 사람의 말)
ANSWER_CHARS = 600
USER_CHARS = 200


def clipped(text: str, limit: int) -> str:
    """앞의 limit 글자. 앞뒤의 빈칸을 지운다."""
    return text.strip()[:limit].strip()


def field_lines(fields: list[tuple[str, str]]) -> list[str]:
    """'이름: 값' 줄들. 비어 있는 칸은 뺀다."""
    return [f'{label}: {value.strip()}' for label, value in fields if value.strip()]


def world_block(briefing: Briefing) -> str:
    """[세계관] 블록."""
    lines = field_lines(
        [('이름', briefing.name), ('소개', clipped(plain_text(briefing.intro_html), WORLD_INTRO_CHARS))]
    )
    return '\n'.join(['[세계관]', *lines])


def member_line(briefing: Briefing, cast_id: str) -> str | None:
    """장면의 인물 한 줄. 판에 없는 인물은 None."""
    member = briefing.member(cast_id)
    if member is None:
        return None
    character = member.character
    fields = [
        ('나이', character.age),
        ('성별', character.gender),
        ('소개', clipped(plain_text(character.intro_html), MEMBER_INTRO_CHARS)),
    ]
    details = ', '.join(f'{label} {value.strip()}' for label, value in fields if value.strip())
    name = character.name or cast_id
    return f'- {name}({details})' if details else f'- {name}'


def scene_block(briefing: Briefing, world: World, state: StoryState, cast: Sequence[str]) -> str:
    """[장면] 블록. 때와 장소는 늘 있고, 장면의 인물은 있을 때만."""
    place = briefing.place(state.place)
    place_name = place.name if place is not None and place.name else state.place
    place_line = f'장소: {place_name} — {place.description}' if place is not None and place.description else ''
    lines = [
        f'때: {day_of(state.minutes)}일째 {briefing.slot_name(slot_of(world, state.minutes))}',
        place_line or f'장소: {place_name}',
    ]
    members = [line for line in (member_line(briefing, cast_id) for cast_id in cast) if line]
    if members:
        lines += ['장면의 인물:', *members]
    return '\n'.join(['[장면]', *lines])


def answer_text(briefing: Briefing, segments: Sequence[Mapping]) -> str:
    """말 조각을 이은 글. 서술(speaker 가 없다)은 글만, 인물의 말은 '이름: 말'이다."""
    lines = []
    for segment in segments:
        text = str(segment.get('text', '')).strip()
        speaker = segment.get('speaker')
        if text:
            lines.append(f'{briefing.cast_name(str(speaker))}: {text}' if speaker else text)
    return '\n'.join(lines)


def moment_block(answer: str, asked: str | None) -> str:
    """[일어나는 일] 블록. 사람의 말이 있으면 먼저 둔다."""
    lines = [f'사용자: {clipped(asked, USER_CHARS)}'] if asked and asked.strip() else []
    lines.append(clipped(answer, ANSWER_CHARS))
    return '\n'.join(['[일어나는 일]', *lines])


def snapshot_prompt(
    briefing: Briefing,
    world: World,
    state: StoryState,
    cast: Sequence[str],
    segments: Sequence[Mapping],
    asked: str | None,
) -> str:
    """그림의 지시 전부. 지킬 것, 세계관, 장면, 일어나는 일의 차례다."""
    blocks = ['\n'.join(RULES), world_block(briefing), scene_block(briefing, world, state, cast)]
    return '\n\n'.join([*blocks, moment_block(answer_text(briefing, segments), asked)])
