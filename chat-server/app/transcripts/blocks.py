# chat-server/app/transcripts/blocks.py

"""
기록의 조각. 대화의 말을 이 조각으로 바꾸고(app/transcripts/story.py), 조각을 형식마다 글로 쓴다
(markdown.py, html.py, text.py). TRPG 의 기록(trpg-server/app/transcripts/blocks.py)과 같은 모양이다.

조각은 형식을 모른다. 굵게, 인용, 제목의 표시는 쓰는 쪽이 정한다. 그래서 세 형식이 같은 내용을 갖는다.
글은 사람과 모델이 쓴 것이다. 쓰는 쪽이 형식에 맞게 막는다(마크다운의 #, HTML 의 꺾쇠).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Heading:
    """구분. 시작 상황, 대화."""

    text: str


@dataclass(frozen=True)
class Paragraph:
    """여러 줄의 글. 시작 상황의 글이다. 빈 줄은 문단의 구분이다."""

    lines: tuple[str, ...]


@dataclass(frozen=True)
class Speech:
    """누가 한 말. 말한 사람(캐릭터나 페르소나의 이름)과 여러 줄의 글."""

    speaker: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class Note:
    """한 줄의 일. 행동(이동, 물건 쓰기, 건네기), 이벤트 씬, 받아들인 상태의 변화, 끊긴 답 같은 것이다."""

    text: str


Block = Heading | Paragraph | Speech | Note


def stands_apart(block: Block) -> bool:
    """앞뒤에 빈 줄을 두는 조각인가. 구분과 문단과 말이다. 한 줄의 일은 이어 쓴다."""
    return not isinstance(block, Note)
