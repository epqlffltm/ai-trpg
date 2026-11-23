# story-server/tests/test_references_parts.py

"""
참고 자료(#1338)를 카드에 넣는 부분을 DB 없이 검증한다. 찾고 넣는 흐름은 공용 코드(conversation_core/lookups.py)다.

  - 블록의 자리: 로어북 뒤, 장면 지시와 쓰는 법 앞. 둘 다 없으면 끝
  - 찾는 글: 판이 허용하고(references_allowed 가 참일 때만) 사람이 켰을 때만 있다. 최근 말 둘이다
  - 판의 허용: 칸이 없는 옛 판, 참이 아닌 값은 허용하지 않은 것이다
"""

from typing import Any, cast

from app.conversations.service import references_allowed
from app.turns.prompt import with_references
from app.turns.service import Branch, references_query

CARD = '[세계관]\n\n[로어북]\n- 탑: 붉은 탑.\n\n[장면 지시]\n비가 온다.\n\n[쓰는 법]\n말하는 사람을 적는다.'
BLOCK = '[참고 자료]\n- [물건] 갤리온: 큰 배.'


def branch(document: dict, enabled: bool) -> Branch:
    nothing = cast(Any, None)
    return Branch(nothing, nothing, [], nothing, document, references_enabled=enabled)


def test_the_block_goes_after_the_lorebook_and_before_the_direction():
    card = with_references(CARD, BLOCK)

    assert card.index('[로어북]') < card.index('[참고 자료]') < card.index('[장면 지시]') < card.index('[쓰는 법]')
    assert with_references('[세계관]', BLOCK) == f'[세계관]\n\n{BLOCK}'


def test_without_a_direction_the_block_goes_before_the_writing_rules():
    card = with_references('[세계관]\n\n[쓰는 법]\n적는다.', BLOCK)

    assert card == f'[세계관]\n\n{BLOCK}\n\n[쓰는 법]\n적는다.'


def test_only_a_true_flag_allows():
    assert references_allowed({'references_allowed': True})
    assert not references_allowed({'references_allowed': False})
    assert not references_allowed({'references_allowed': 'yes'})
    assert not references_allowed({})


def test_the_query_needs_both_the_creator_and_the_person():
    recent = ['어서 와요.', '저 갤리온 좀 봐', '갤리온?']
    allowed = {'references_allowed': True}

    assert references_query(branch(allowed, enabled=True), recent) == '저 갤리온 좀 봐\n갤리온?'
    assert references_query(branch(allowed, enabled=False), recent) is None
    assert references_query(branch({}, enabled=True), recent) is None
