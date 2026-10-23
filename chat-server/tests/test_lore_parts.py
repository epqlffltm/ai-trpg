# chat-server/tests/test_lore_parts.py

"""
로어북을 뜻으로 찾는 일의 순수한 부분(#672).
app/lore/texts.py, recall.py 의 nearest, app/turns/prompt.py 의 with_lore 다.
DB 도 모델도 쓰지 않는다.

보는 것.
  - 항목은 이름, 키워드, 내용을 합친 글로 바꾼다. 열쇠는 (로어북의 id, 항목의 id)다.
    벡터가 없는 것만 고른다(같은 열쇠는 한 번)
  - 묶음의 크기
  - 가까운 것: 거리 상한 안에서 가까운 것부터, 이미 고른 것은 빼고, 개수의 상한까지
  - 카드의 "[로어북]" 바꾸기: 있던 블록을 바꾸고, 없으면 지금 블록 앞에 넣는다. 같거나 없으면 그대로다
"""

import uuid

from app.assets.schemas import LoreEntryDocument
from app.lore.recall import MAX_DISTANCE, RECALL_MAX, nearest
from app.lore.texts import BATCH_SIZE, KeyedEntry, batches, entry_text, keyed_entries, missing_entries
from app.turns.prompt import with_lore
from tests.assets import make_character

BOOK = uuid.UUID('0c1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d')
OTHER = uuid.UUID('1c1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d')


def entry(entry_id: str, keywords: list[str] | None = None) -> LoreEntryDocument:
    return LoreEntryDocument(id=entry_id, name=f'{entry_id} 이름', keywords=keywords or [], content=f'{entry_id} 내용')


def test_the_text_joins_name_keywords_and_content():
    assert entry_text(entry('tower', ['탑', '마탑'])) == 'tower 이름\n키워드: 탑, 마탑\ntower 내용'
    assert entry_text(entry('river')) == 'river 이름\nriver 내용'


def test_entries_are_keyed_by_lorebook_and_id():
    books = [
        {'id': str(BOOK), 'version': 1, 'name': '하나', 'entries': [entry('a').model_dump()]},
        {'id': str(OTHER), 'version': 1, 'name': '둘', 'entries': [entry('a').model_dump(), entry('b').model_dump()]},
    ]
    document = make_character(world={'lorebooks': books}).document

    assert [item.key for item in keyed_entries(document)] == [(BOOK, 'a'), (OTHER, 'a'), (OTHER, 'b')]


def test_only_missing_entries_are_embedded_once():
    keyed = [
        KeyedEntry((BOOK, 'a'), entry('a')),
        KeyedEntry((BOOK, 'b'), entry('b')),
        KeyedEntry((BOOK, 'b'), entry('b')),
    ]

    assert [item.key for item in missing_entries(keyed, {(BOOK, 'a')})] == [(BOOK, 'b')]


def test_batches_have_a_size_limit():
    keyed = [KeyedEntry((BOOK, f'e{number}'), entry(f'e{number}')) for number in range(BATCH_SIZE + 1)]

    assert [len(batch) for batch in batches(keyed)] == [BATCH_SIZE, 1]


def test_the_nearest_within_the_limit_come_first():
    keys = [(BOOK, name) for name in 'abcdef']
    distances = {
        keys[0]: 0.1,
        keys[1]: 0.05,
        keys[2]: MAX_DISTANCE,
        keys[3]: MAX_DISTANCE + 0.01,
        keys[4]: 0.2,
    }

    assert nearest(keys, distances, exclude=[0]) == [1, 4, 2]
    assert len(nearest(keys, dict.fromkeys(keys, 0.0), exclude=[])) == RECALL_MAX


def test_equal_distances_keep_the_book_order():
    keys = [(BOOK, 'a'), (BOOK, 'b')]

    assert nearest(keys, dict.fromkeys(keys, 0.3), exclude=[]) == [0, 1]


CARD = '[지킬 것]\n규칙\n\n[기억]\n- 메모\n\n[지금]\n시각: 낮'


def test_an_old_block_is_replaced():
    card = CARD.replace('\n\n[지금]', '\n\n[로어북]\n- 옛것\n\n[지금]')

    assert with_lore(card, '[로어북]\n- 옛것', '[로어북]\n- 새것') == CARD.replace(
        '\n\n[지금]', '\n\n[로어북]\n- 새것\n\n[지금]'
    )


def test_without_an_old_block_it_goes_before_now():
    assert with_lore(CARD, None, '[로어북]\n- 새것') == CARD.replace('\n\n[지금]', '\n\n[로어북]\n- 새것\n\n[지금]')


def test_without_now_it_goes_at_the_end():
    assert with_lore('[지킬 것]\n규칙', None, '[로어북]\n- 새것') == '[지킬 것]\n규칙\n\n[로어북]\n- 새것'


def test_nothing_new_keeps_the_card():
    assert with_lore(CARD, None, None) == CARD
    assert with_lore(CARD, '[로어북]\n- 같다', '[로어북]\n- 같다') == CARD
