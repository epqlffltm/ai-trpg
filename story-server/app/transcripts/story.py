# story-server/app/transcripts/story.py

"""
세션의 말들을 기록의 조각으로 바꾼다. DB 와 HTTP 를 모른다. 받는 것은 이미 읽은 말들과 세션의 머리다.

  - 넣는 것: 지금 보고 있는 가지의 말(첫 말부터), 행동(서버가 쓴 글 그대로), 열린 이벤트와 본 엔딩의 이름,
    끊긴 답과 고친 답의 표시. 모두 세션 화면에서 그 사람이 본 것이다
  - 넣지 않는 것: 다른 가지(대안), 다음 답 추천, 이벤트의 선택지(고른 것은 행동 말로 남는다), 표정,
    기억 메모와 요약, 모델에게만 가는 글(세계관의 소개, 인물의 설정, 로어북, 이벤트의 장면 지시)
  - 사람의 말은 페르소나의 이름(없으면 "나")으로 적는다. 답은 말 조각마다 적는다.
    서술은 말한 사람이 없는 문단이고, 인물의 말은 판의 이름이다. 같은 사람이 이어 말한 조각은 하나로 묶는다(화면과 같다)
  - 인물, 이벤트, 엔딩은 판의 이름으로 적는다. 판에 없는 id 이거나 이름이 비었으면 id 를 그대로 적는다
"""

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import groupby

from app.conversations.models import Message, MessageStatus, Role
from app.engine.world import World
from app.transcripts.blocks import Block, Heading, Note, Paragraph, Speech
from app.turns.briefing import Briefing
from app.turns.segments import Segment, segments_of

# 페르소나 없이 시작한 세션에서 사람의 말을 적는 이름
SELF = '나'


@dataclass(frozen=True)
class Head:
    """세션의 머리. 파일의 제목과 범위, 사람의 이름, 판의 이름표(글과 규칙)."""

    title: str
    world: str
    version: int
    persona: str | None
    message_count: int
    briefing: Briefing
    rules: World


def lines_of(text: str) -> tuple[str, ...]:
    """글을 줄로 나눈다. 줄 끝의 빈칸은 뗀다."""
    return tuple(line.rstrip() for line in text.strip('\n').split('\n'))


def event_name(rules: World, event_id: str) -> str:
    """그 id 의 이벤트의 이름. 없거나 이름이 비었으면 id 그대로다."""
    event = rules.event(event_id)
    return event.name if event is not None and event.name else event_id


def ending_name(rules: World, ending_id: str) -> str:
    """그 id 의 엔딩의 이름. 없거나 이름이 비었으면 id 그대로다."""
    ending = rules.ending(ending_id)
    return ending.name if ending is not None and ending.name else ending_id


def segment_lines(segments: list[Segment]) -> tuple[str, ...]:
    """이어진 조각들의 줄. 조각 하나가 한 줄 이상이다."""
    return tuple(line for segment in segments for line in lines_of(segment.text))


def answer_blocks(segments: tuple[Segment, ...], briefing: Briefing) -> Iterator[Block]:
    """답의 조각들. 같은 사람이 이어 말한 조각은 하나로 묶는다. 서술은 문단, 인물의 말은 그 이름의 말이다."""
    for speaker, run in groupby(segments, key=lambda segment: segment.speaker):
        lines = segment_lines(list(run))
        if speaker is None:
            yield Paragraph(lines)
        else:
            yield Speech(briefing.cast_name(speaker), lines)


def said_blocks(message: Message, head: Head) -> Iterator[Block]:
    """말 하나의 글. 사람의 말, 행동, 답 가운데 하나다. 조각이 없는 답(옛 말)은 본문을 서술로 적는다."""
    if message.role == Role.USER:
        yield Speech(head.persona or SELF, lines_of(message.content))
    elif message.role == Role.ACTION:
        yield Note(message.content.strip())
    elif message.segments:
        yield from answer_blocks(segments_of(message.segments), head.briefing)
    elif message.content.strip():
        yield Paragraph(lines_of(message.content))


def mark_blocks(message: Message, head: Head) -> Iterator[Block]:
    """말에 붙은 표시. 끊긴 답, 고친 답, 그 행동 뒤에 열린 이벤트와 본 엔딩이다."""
    if message.status == MessageStatus.PARTIAL:
        yield Note('여기서 끊긴 답이다')
    if message.edited:
        yield Note('고친 답이다')
    if message.event_id:
        yield Note(f'이벤트: {event_name(head.rules, message.event_id)}')
    if message.ending_id:
        yield Note(f'엔딩: {ending_name(head.rules, message.ending_id)}')


def message_blocks(message: Message, head: Head) -> Iterator[Block]:
    """말 하나의 조각들. 글, 그다음 표시다."""
    yield from said_blocks(message, head)
    yield from mark_blocks(message, head)


def transcript_blocks(head: Head, messages: list[Message]) -> Iterator[Block]:
    """기록 전체의 조각. 세션을 시작할 때 말이 없으므로 구분 하나 아래에 말들이다."""
    yield Heading('이야기')
    for message in messages:
        yield from message_blocks(message, head)


def scope_text(head: Head) -> str:
    """파일의 머리에 적는 범위."""
    return f'{head.world}({head.version}번째 판), 지금 보는 가지의 말 {head.message_count}개'
