# shared/conversation-core/tests/test_lorebook.py

"""
로어북의 항목을 고르는 규칙(conversation_core/lorebook.py, #672). DB 도 모델도 쓰지 않는다.

보는 것.
  - 상시 항목은 늘 들어간다. 나머지는 최근 말(SCAN_MESSAGES 개)에 키워드가 나와야 들어간다
  - 키워드는 대소문자를 가리지 않고, 조사가 붙어도 맞는다. 빈 키워드는 보지 않는다. 오래된 말의 키워드는 보지 않는다
  - 차례: 상시가 먼저(판의 차례), 그다음 키워드가 가장 최근에 나온 것부터(같으면 판의 차례)
  - 상한: 항목의 수, 글자(들어가지 않는 것은 건너뛰고 다음 것을 본다)
  - 뜻으로 찾은 항목은 키워드로 고른 것 뒤에 붙는다(이미 고른 것은 빠진다). 찾는 글은 최근 말 둘이다
  - 블록의 모양. 항목이 없으면 블록이 없다
"""

from dataclasses import dataclass, field

from conversation_core.lorebook import (
    MAX_CHARS,
    MAX_ENTRIES,
    QUERY_MESSAGES,
    SCAN_MESSAGES,
    chosen_entries,
    query_text,
    ranked,
    render_lore,
    with_recalled,
)


@dataclass(frozen=True)
class Entry:
    """항목의 모양(LoreEntry)을 따르는 시험용 항목. 쓰는 서버의 것(chat 의 LoreEntryDocument)과 같은 칸이다."""

    name: str
    content: str
    keywords: list[str] = field(default_factory=list)
    constant: bool = False


def entry(entry_id: str, keywords: list[str] | None = None, constant: bool = False, content: str = '설정.'):
    return Entry(name=entry_id, content=content, keywords=keywords or [], constant=constant)


def names(entries) -> list[str]:
    return [item.name for item in entries]


def select_entries(entries, recent):
    return chosen_entries(entries, ranked(entries, recent))


def test_constant_entries_always_go_in():
    entries = [entry('emperor', constant=True), entry('city', ['수도'])]

    assert names(select_entries(entries, ['안녕'])) == ['emperor']


def test_keywords_match_without_case_and_with_particles():
    entries = [entry('rome', ['Rome']), entry('city', ['가나폴리아']), entry('moon', ['달'])]

    picked = select_entries(entries, ['I love ROME.', '가나폴리아에 가 봤어?'])

    assert names(picked) == ['city', 'rome']


def test_old_messages_are_not_scanned():
    recent = ['가나폴리아 이야기', *['그냥 말'] * SCAN_MESSAGES]

    assert select_entries([entry('city', ['가나폴리아'])], recent) == []


def test_blank_keywords_are_ignored():
    assert select_entries([entry('blank', [' '])], ['아무 말']) == []


def test_constant_first_then_the_most_recent_mention():
    entries = [entry('a', ['사과']), entry('b', ['바나나']), entry('c', ['체리']), entry('k', constant=True)]

    picked = select_entries(entries, ['체리가 좋아', '사과랑 바나나', '바나나 말고'])

    assert names(picked) == ['k', 'b', 'a', 'c']


def test_ties_keep_the_book_order():
    entries = [entry('first', ['칼']), entry('second', ['칼'])]

    assert names(select_entries(entries, ['칼을 든다'])) == ['first', 'second']


def test_the_number_of_entries_is_capped():
    entries = [entry(f'e{number}', constant=True) for number in range(MAX_ENTRIES + 2)]

    assert len(select_entries(entries, [])) == MAX_ENTRIES


def test_entries_that_do_not_fit_are_skipped():
    big = 'x' * (MAX_CHARS - 10)
    entries = [
        entry('big', constant=True, content=big),
        entry('also', constant=True, content=big),
        entry('s', constant=True),
    ]

    assert names(select_entries(entries, [])) == ['big', 's']


def test_the_block_lists_names_and_contents():
    assert render_lore([entry('city', content='제국의 수도.')]) == '[로어북]\n- city: 제국의 수도.'
    assert render_lore([]) is None


def test_recalled_entries_follow_the_keyword_ones():
    assert with_recalled([2, 0], [1, 0, 3]) == [2, 0, 1, 3]


def test_the_query_is_the_last_messages():
    recent = ['오래된 말', '앞의 답', '이번 말']

    assert query_text(recent) == '\n'.join(recent[-QUERY_MESSAGES:]) == '앞의 답\n이번 말'
