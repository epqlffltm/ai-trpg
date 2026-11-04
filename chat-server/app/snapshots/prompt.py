# chat-server/app/snapshots/prompt.py

"""
장면 그림의 지시(#983). DB 도 모델도 모르는 순수 함수다.

  - 인물은 대화가 가져온 판의 사본에서(이름, 나이, 성별, 소개의 글자), 시각과 장소와 차림은 서버의 상태에서 온다.
    모델이 글로 지어낸 상태(장소를 옮겼다, 옷을 갈아입었다)를 쓰지 않는다
  - 일어나는 일은 그 답의 글(과 그 답이 답한 사람의 말)에서 앞의 몇 글자만 쓴다
  - 맨 앞에 지킬 것을 둔다. 모든 등급에서 전체이용가로 그린다(성인 그림은 따로 정할 때까지 만들지 않는다)
  - 참고 그림을 넘기면 끝에 [참고 그림] 블록으로 몇 번째 그림이 누구인지 적는다. 받은 그림으로만 적는다(그릴 때 붙인다)
"""

from app.assets.schemas import CharacterDocument
from app.turns.prompt import plain_text
from app.world.scene import outfit_line, place_line, time_line
from app.world.state import WorldState

# 지킬 것. 모든 등급에서 같다
RULES = (
    '대화의 한 장면을 그린 그림 한 장이다.',
    '전체이용가로 그린다. 노출, 성적인 묘사, 잔혹한 묘사를 넣지 않는다.',
    '글자, 말풍선, 서명, 워터마크를 넣지 않는다.',
)
# 참고 그림을 넘길 때 덧붙이는 것
REFERENCE_RULE = '그림 속 인물의 얼굴, 머리 모양, 체형을 참고 그림에 맞춘다. 참고 그림의 배경과 구도는 따르지 않는다.'
# 소개에서 쓰는 글자 수
INTRO_CHARS = 300
# 일어나는 일에서 쓰는 글자 수(답, 사람의 말)
ANSWER_CHARS = 600
USER_CHARS = 200


def clipped(text: str, limit: int) -> str:
    """앞의 limit 글자. 앞뒤의 빈칸을 지운다."""
    return text.strip()[:limit].strip()


def character_block(document: CharacterDocument) -> str:
    """[인물] 블록. 비어 있는 칸은 뺀다."""
    fields = [
        ('이름', document.name),
        ('나이', document.age),
        ('성별', document.gender),
        ('소개', clipped(plain_text(document.intro_html), INTRO_CHARS)),
    ]
    lines = [f'{label}: {value.strip()}' for label, value in fields if value.strip()]
    return '\n'.join(['[인물]', *lines])


def scene_block(document: CharacterDocument, state: WorldState, start_hour: int) -> str:
    """[장면] 블록. 시각은 늘 있고, 장소와 차림은 있을 때만."""
    lines = [time_line(state, start_hour), place_line(document, state), outfit_line(document, state)]
    return '\n'.join(['[장면]', *(line for line in lines if line)])


def moment_block(answer: str, asked: str | None) -> str:
    """[일어나는 일] 블록. 사람의 말이 있으면 먼저 둔다."""
    lines = []
    if asked and asked.strip():
        lines.append(f'사용자: {clipped(asked, USER_CHARS)}')
    lines.append(f'{clipped(answer, ANSWER_CHARS)}')
    return '\n'.join(['[일어나는 일]', *lines])


def snapshot_prompt(
    document: CharacterDocument, state: WorldState, start_hour: int, answer: str, asked: str | None
) -> str:
    """그림의 지시 전부. 지킬 것, 인물, 장면, 일어나는 일의 차례다."""
    blocks = ['\n'.join(RULES), character_block(document), scene_block(document, state, start_hour)]
    return '\n\n'.join([*blocks, moment_block(answer, asked)])


def reference_block(names: list[str]) -> str:
    """[참고 그림] 블록. 넘긴 차례대로 그 그림의 인물을 적는다."""
    lines = [f'{index}번째 그림: {name}' for index, name in enumerate(names, start=1)]
    return '\n'.join(['[참고 그림]', *lines, REFERENCE_RULE])


def with_references(prompt: str, names: list[str]) -> str:
    """참고 그림이 있으면 지시 끝에 [참고 그림] 블록을 붙인다. 없으면 그대로."""
    return prompt if not names else f'{prompt}\n\n{reference_block(names)}'
