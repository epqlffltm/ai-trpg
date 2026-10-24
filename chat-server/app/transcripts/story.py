# chat-server/app/transcripts/story.py

"""
대화의 말들을 기록의 조각으로 바꾼다. DB 와 HTTP 를 모른다. 받는 것은 이미 읽은 말들과 대화의 머리다.

  - 넣는 것: 시작 상황, 지금 보고 있는 가지의 말(첫 말부터), 행동, 이벤트 씬, 받아들인 상태의 변화, 끊긴 답의 표시.
    모두 대화 화면에서 그 사람이 본 것이다
  - 넣지 않는 것: 다른 가지(대안), 다음 답 추천의 선택지, 표정, 기억 메모와 요약, 모델에게만 가는 글
    (캐릭터의 설정, 로어북, 이벤트 씬의 설명). 화면에 보이지 않거나 대화가 아니다
  - 사람의 말은 페르소나의 이름(없으면 "나"), 캐릭터의 말은 캐릭터의 이름으로 적는다. 행동 말은 서버가 쓴 글 그대로다
  - 장소와 물건과 이벤트 씬은 판의 이름으로 적는다. 판에 없는 id 면 id 를 그대로 적는다
"""

from collections.abc import Iterator
from dataclasses import dataclass

from app.assets.schemas import CharacterDocument
from app.conversations.models import Message, MessageStatus, Role
from app.transcripts.blocks import Block, Heading, Note, Paragraph, Speech

# 페르소나 없이 시작한 대화에서 사람의 말을 적는 이름
SELF = '나'


@dataclass(frozen=True)
class Head:
    """대화의 머리. 파일의 제목과 범위, 말한 사람의 이름, 판의 이름표."""

    title: str
    character: str
    version: int
    start_title: str
    start_situation: str
    persona: str | None
    message_count: int
    document: CharacterDocument


def lines_of(text: str) -> tuple[str, ...]:
    """글을 줄로 나눈다. 줄 끝의 빈칸은 뗀다."""
    return tuple(line.rstrip() for line in text.strip('\n').split('\n'))


def place_name(document: CharacterDocument, place_id: str) -> str:
    return next((place.name for place in document.places if place.id == place_id and place.name), place_id)


def item_name(document: CharacterDocument, item_id: str) -> str:
    return next((item.name for item in document.items if item.id == item_id and item.name), item_id)


def scene_title(document: CharacterDocument, scene_id: str) -> str:
    return next((scene.title for scene in document.event_scenes if scene.id == scene_id), scene_id)


def change_text(change: dict, document: CharacterDocument) -> str | None:
    """받아들인 상태의 변화 하나(app/world/proposals.py)의 글. 모르는 종류면 None."""
    kind = change.get('kind')
    if kind == 'affection':
        way = '올랐다' if change.get('rising') else '내렸다'
        delta = change.get('delta')
        return f'호감도가 {way}({delta:+d})' if isinstance(delta, int) else f'호감도가 {way}'
    if kind == 'gift':
        return f'받은 물건: {item_name(document, str(change.get("item", "")))}'
    if kind == 'move':
        return f'함께 간 곳: {place_name(document, str(change.get("place", "")))}({change.get("minutes", 0)}분)'
    return None


def speaker_of(message: Message, head: Head) -> str:
    """말한 사람의 이름. 사람이 고친 캐릭터의 말이면 표시를 단다."""
    if message.role == Role.USER:
        return head.persona or SELF
    return f'{head.character}(고침)' if message.edited else head.character


def message_blocks(message: Message, head: Head) -> Iterator[Block]:
    """말 하나의 조각들. 글자 하나 없이 실패한 답은 쓰지 않는다."""
    if message.status == MessageStatus.FAILED and not message.content.strip():
        return
    if message.role == Role.ACTION:
        yield Note(message.content.strip())
    else:
        yield Speech(speaker_of(message, head), lines_of(message.content))
    if message.status == MessageStatus.PARTIAL:
        yield Note('여기서 끊긴 답이다')
    for change in message.changes or []:
        text = change_text(change, head.document)
        if text is not None:
            yield Note(text)
    if message.event_scene:
        yield Note(f'이벤트 씬: {scene_title(head.document, message.event_scene)}')


def transcript_blocks(head: Head, messages: list[Message]) -> Iterator[Block]:
    """기록 전체의 조각. 시작 상황, 그다음 말들이다."""
    yield Heading(f'시작 상황: {head.start_title}')
    if head.start_situation.strip():
        yield Paragraph(lines_of(head.start_situation))
    yield Heading('대화')
    for message in messages:
        yield from message_blocks(message, head)


def scope_text(head: Head) -> str:
    """파일의 머리에 적는 범위."""
    return f'{head.character}({head.version}번째 판), 지금 보는 가지의 말 {head.message_count}개'
