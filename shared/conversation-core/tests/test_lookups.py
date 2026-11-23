# shared/conversation-core/tests/test_lookups.py

"""
모델을 부르기 직전의 두 찾기(conversation_core/lookups.py). DB 도 모델도 쓰지 않는다. 서버의 것 대신 가짜를 넘긴다.

보는 것.
  - 로어북: 뜻으로 찾은 항목을 키워드로 고른 것 뒤에 붙여 카드와 바탕(블록, 글자)을 바꾼다. 못 찾으면 그대로다
  - 참고 자료: 로어북이 쓴 글자와 상한을 넘기고, 받은 블록을 카드에 넣는다. 끄거나 못 찾으면 그대로다
  - 카드 말고 다른 메시지는 바뀌지 않는다
"""

from dataclasses import dataclass, field

from conversation_core.lookups import lore_chars, with_card, with_found_references, with_recalled_lore
from conversation_core.lorebook import MAX_CHARS


@dataclass
class Entry:
    name: str
    content: str
    keywords: list[str] = field(default_factory=list)
    constant: bool = False


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class Plan:
    entries: tuple[Entry, ...]
    ranked: tuple[int, ...]
    block: str | None
    chars: int = 0


@dataclass(frozen=True)
class Start:
    messages: list[Message]
    lore: Plan | None = None
    references: str | None = None


@dataclass
class Recall:
    found: list[int]
    plans: list[Plan] = field(default_factory=list)

    async def recall(self, plan: Plan) -> list[int]:
        self.plans.append(plan)
        return self.found


@dataclass
class Finder:
    block: str | None
    calls: list[tuple[str, int, int]] = field(default_factory=list)

    async def block_after(self, text: str, used: int, budget: int) -> str | None:
        self.calls.append((text, used, budget))
        return self.block


KING = Entry('왕', '늙은 왕.')
TOWER = Entry('탑', '붉은 탑.')
CARD = '[캐릭터]\n\n[로어북]\n- 왕: 늙은 왕.\n\n[지금]'
USER = Message('user', '탑에 가자')


def start(lore: Plan | None = None, references: str | None = None) -> Start:
    return Start(messages=[Message('system', CARD), USER], lore=lore, references=references)


def swap(card: str, old: str | None, new: str | None) -> str:
    return card.replace(old or '', new or '')


def insert(card: str, block: str) -> str:
    return card.replace('\n\n[지금]', f'\n\n{block}\n\n[지금]')


def test_the_chars_are_names_and_contents():
    assert lore_chars([KING, TOWER]) == len('왕늙은 왕.탑붉은 탑.')
    assert lore_chars([]) == 0


def test_with_card_changes_only_the_card():
    changed = with_card(start(), '새 카드')

    assert changed.messages == [Message('system', '새 카드'), USER]


async def test_recalled_entries_change_the_card_and_the_basis():
    plan = Plan(entries=(KING, TOWER), ranked=(0,), block='[로어북]\n- 왕: 늙은 왕.', chars=lore_chars([KING]))
    recall = Recall(found=[1])

    changed = await with_recalled_lore(recall, start(plan), swap)

    assert '- 탑: 붉은 탑.' in changed.messages[0].content
    assert changed.lore is not None
    assert changed.lore.block == '[로어북]\n- 왕: 늙은 왕.\n- 탑: 붉은 탑.'
    assert changed.lore.chars == lore_chars([KING, TOWER])
    assert recall.plans == [plan]


async def test_nothing_recalled_keeps_the_turn():
    plan = Plan(entries=(KING,), ranked=(0,), block=None)
    before = start(plan)

    assert await with_recalled_lore(Recall(found=[]), before, swap) is before
    assert await with_recalled_lore(None, before, swap) is before
    assert await with_recalled_lore(Recall(found=[0]), start(), swap) == start()


async def test_references_get_what_the_lorebook_left():
    finder = Finder(block='[참고 자료]\n- [물건] 갤리온: 큰 배.')
    plan = Plan(entries=(KING,), ranked=(0,), block='[로어북]', chars=120)

    changed = await with_found_references(finder, start(plan, references='갤리온'), insert)

    assert changed.messages[0].content.index('[로어북]') < changed.messages[0].content.index('[참고 자료]')
    assert changed.messages[0].content.index('[참고 자료]') < changed.messages[0].content.index('[지금]')
    assert finder.calls == [('갤리온', 120, MAX_CHARS)]


async def test_without_a_lorebook_nothing_is_used():
    finder = Finder(block=None)

    changed = await with_found_references(finder, start(references='갤리온'), insert)

    assert changed == start(references='갤리온')
    assert finder.calls == [('갤리온', 0, MAX_CHARS)]


async def test_switched_off_references_are_not_looked_up():
    finder = Finder(block='[참고 자료]')

    assert await with_found_references(finder, start(), insert) == start()
    assert await with_found_references(None, start(references='갤리온'), insert) == start(references='갤리온')
    assert finder.calls == []
