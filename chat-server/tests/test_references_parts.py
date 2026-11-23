# chat-server/tests/test_references_parts.py

"""
참고 자료(#1338)를 카드에 넣는 부분을 DB 없이 검증한다.

  - 블록의 자리: 로어북 뒤, 지금 앞. 지금 블록이 없으면 끝
  - 남은 자리: 제작자의 로어북이 쓰고 남은 글자만큼만 찾는다. 다 썼으면 찾지 않는다
  - 켜지 않았거나 찾는 것이 없으면 카드는 그대로다
  - 찾는 글: 판이 허용하고 사람이 켰을 때만 있다
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ai_core.provider import ChatMessage, Role
from conversation_core.lookups import with_found_references
from conversation_core.lorebook import MAX_CHARS as LORE_MAX_CHARS
from reference_core.prompt import render_references
from reference_core.records import ReferenceKind, StoredReference
from reference_core.selection import REFERENCE_MAX_CHARS, room_after

from app.conversations.models import Conversation
from app.turns.prompt import with_references
from app.turns.service import references_query
from app.turns.values import LorePlan, SavedMessage, TurnStart
from tests.assets import make_character

CARD = '[캐릭터]\n이름: 세라\n\n[로어북]\n- 왕: 늙은 왕.\n\n[지금]\n장소: 도서관'
GALLEON = StoredReference(
    id=uuid.uuid4(), key='g', name='Galleon', kind=ReferenceKind.ITEM, content_ko='큰 배.', name_ko='갤리온'
)


@dataclass
class RecordingFinder:
    """받은 글과 자리를 적고, 정해 둔 줄로 블록을 만든다(reference_core/finder.py 의 block_after 와 같은 셈)."""

    found: list[StoredReference] = field(default_factory=list)
    calls: list[tuple[str, int]] = field(default_factory=list)

    async def block_after(self, text: str, used: int, budget: int) -> str | None:
        self.calls.append((text, room_after(used, budget)))
        return render_references(self.found)


def turn(references: str | None, lore_chars: int | None = None) -> TurnStart:
    now = datetime(2026, 11, 23, tzinfo=UTC)
    message = SavedMessage(
        id=uuid.uuid4(), parent_id=None, role='user', content='갤리온', status='complete', created_at=now
    )
    lore = None
    if lore_chars is not None:
        lore = LorePlan(uuid.uuid4(), (), (), (), query='', block='[로어북]\n- 왕: 늙은 왕.', chars=lore_chars)
    return TurnStart(
        conversation_id=uuid.uuid4(),
        generation_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        model_slug='luna',
        reference='r',
        price_code='chat.luna.i0.o0',
        user_message=message,
        messages=[ChatMessage(role=Role.SYSTEM, content=CARD), ChatMessage(role=Role.USER, content='갤리온')],
        lore=lore,
        references=references,
    )


def test_the_block_goes_after_the_lorebook_and_before_now():
    card = with_references(CARD, '[참고 자료]\n- [물건] 갤리온: 큰 배.')

    assert card.index('[로어북]') < card.index('[참고 자료]') < card.index('[지금]')
    assert with_references(CARD, None) == CARD
    assert with_references('[캐릭터]', '[참고 자료]') == '[캐릭터]\n\n[참고 자료]'


async def test_found_references_are_added_to_the_card():
    finder = RecordingFinder(found=[GALLEON])

    start = await with_found_references(finder, turn('갤리온'), with_references)

    assert '- [물건] 갤리온: 큰 배.' in start.messages[0].content
    assert start.messages[1:] == turn('갤리온').messages[1:]
    assert finder.calls == [('갤리온', REFERENCE_MAX_CHARS)]


async def test_the_room_is_what_the_lorebook_left():
    finder = RecordingFinder()

    await with_found_references(finder, turn('갤리온', lore_chars=LORE_MAX_CHARS - 100), with_references)
    await with_found_references(finder, turn('갤리온', lore_chars=LORE_MAX_CHARS), with_references)

    assert finder.calls == [('갤리온', 100), ('갤리온', 0)]


async def test_nothing_changes_when_off_or_nothing_is_found():
    finder = RecordingFinder()

    off = await with_found_references(finder, turn(None), with_references)
    none_found = await with_found_references(finder, turn('갤리온'), with_references)
    no_finder = await with_found_references(None, turn('갤리온'), with_references)

    assert off.messages[0].content == none_found.messages[0].content == no_finder.messages[0].content == CARD
    assert finder.calls == [('갤리온', REFERENCE_MAX_CHARS)]


def test_the_query_needs_both_the_creator_and_the_person():
    allowed = make_character(world={'references_allowed': True}).document
    closed = make_character().document
    on, off = Conversation(references_enabled=True), Conversation(references_enabled=False)
    recent = ['어서 와요.', '저 갤리온 좀 봐', '갤리온?']

    assert references_query(on, allowed, recent) == '저 갤리온 좀 봐\n갤리온?'
    assert references_query(off, allowed, recent) is None
    assert references_query(on, closed, recent) is None
