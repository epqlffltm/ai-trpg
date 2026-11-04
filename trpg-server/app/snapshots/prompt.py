# trpg-server/app/snapshots/prompt.py

"""
장면 그림의 지시(#983). DB 도 모델도 모르는 순수 함수다.

  - 그리는 것은 그 라운드의 장면(앉은 사람 모두에게 보이는 GM 의 서술)과 테이블의 제목, 앉은 캐릭터의 이름이다.
    판의 GM 전용 글(테이블의 content)은 넣지 않는다. 그림을 보는 사람은 앉은 사람 모두다
  - 장면은 앞의 몇 글자만 쓴다
  - 맨 앞에 지킬 것을 둔다. 모든 등급에서 전체이용가로 그린다(성인 그림은 따로 정할 때까지 만들지 않는다)
"""

from collections.abc import Sequence

# 지킬 것. 모든 등급에서 같다
RULES = (
    'TRPG 한 장면을 그린 그림 한 장이다.',
    '전체이용가로 그린다. 노출, 성적인 묘사, 잔혹한 묘사를 넣지 않는다.',
    '글자, 말풍선, 서명, 워터마크, 주사위나 게임판의 화면을 넣지 않는다.',
)
# 장면에서 쓰는 글자 수
SCENE_CHARS = 800
# 이름을 넣는 캐릭터의 수
MAX_NAMES = 6


def clipped(text: str, limit: int) -> str:
    """앞의 limit 글자. 앞뒤의 빈칸을 지운다."""
    return text.strip()[:limit].strip()


def story_block(title: str, round_number: int, names: Sequence[str]) -> str:
    """[이야기] 블록. 제목과 몇 번째 장면인지, 앉은 캐릭터의 이름(있을 때만)."""
    lines = [f'제목: {title.strip()}' if title.strip() else '', f'{round_number}번째 장면']
    shown = [name.strip() for name in names if name.strip()][:MAX_NAMES]
    if shown:
        lines.append(f'일행: {", ".join(shown)}')
    return '\n'.join(['[이야기]', *(line for line in lines if line)])


def scene_block(scene: str) -> str:
    """[장면] 블록. GM 의 서술의 앞의 몇 글자."""
    return '\n'.join(['[장면]', clipped(scene, SCENE_CHARS)])


def snapshot_prompt(title: str, round_number: int, names: Sequence[str], scene: str) -> str:
    """그림의 지시 전부. 지킬 것, 이야기, 장면의 차례다."""
    return '\n\n'.join(['\n'.join(RULES), story_block(title, round_number, names), scene_block(scene)])
