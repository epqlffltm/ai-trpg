# shared/reference-core/tests/test_selection.py

"""
장면에 넣을 참고 자료를 고르는 규칙(reference_core/selection.py)을 검증한다. DB 도 모델도 쓰지 않는다.

보는 것.
  - 다른 이름: 글에 그대로 들어 있으면 걸린다. 대소문자를 가리지 않고, 한 글자 이름은 보지 않는다
  - 거리: 다른 이름으로 걸려도 멀면 넣지 않는다. 거리를 모르면(벡터가 없다) 넣는다
  - 자리: 다른 이름으로 걸린 것이 먼저, 그다음 뜻이 가까운 것. 글자 수와 수의 상한, 같은 줄은 한 번
"""

import uuid

from reference_core.records import StoredReference
from reference_core.selection import (
    ReferenceThresholds,
    alias_hits,
    choose,
    mentions_alias,
    near_enough,
    pick,
    reference_size,
)


def stored(name: str, aliases: list[str] | None = None, content: str = '', **values) -> StoredReference:
    return StoredReference(id=uuid.uuid4(), key=name, name=name, aliases=aliases or [], content=content, **values)


def test_an_alias_in_the_text_is_found_whatever_the_case():
    ship = stored('Galleon', ['갤리온', 'Galleon'])

    assert mentions_alias(ship, '항구에 GALLEON 한 척이 서 있다')
    assert mentions_alias(ship, '갤리온이 들어온다')
    assert not mentions_alias(ship, '작은 배가 들어온다')


def test_a_one_letter_alias_is_not_seen():
    rat = stored('Rat', ['쥐'])
    rats = stored('Swarm of Rats', [' 쥐 떼 '])

    assert alias_hits([rat, rats], '검을 쥐었다. 쥐 떼가 몰려온다') == [rats]


def test_a_far_alias_hit_is_left_out_but_an_unmeasured_one_is_kept():
    hit = stored('Bat', ['박쥐'])

    assert near_enough(hit, {hit.id: 0.3}, 0.5)
    assert not near_enough(hit, {hit.id: 0.6}, 0.5)
    assert near_enough(hit, {}, 0.5)


def test_the_size_is_the_shown_name_and_text():
    english = stored('Torch', content='A torch.')
    korean = stored('Torch', content='A torch.', name_ko='횃불', content_ko='탄다.')

    assert reference_size(english) == len('Torch') + len('A torch.')
    assert reference_size(korean) == len('횃불') + len('탄다.')


def test_picking_skips_what_does_not_fit_and_stops_at_the_limit():
    long_one, short_one, other = stored('a', content='x' * 50), stored('b', content='y'), stored('c', content='z')

    assert pick([long_one, short_one, other], room=10, limit=5) == [short_one, other]
    assert pick([short_one, short_one, other], room=10, limit=5) == [short_one, other]
    assert pick([short_one, other, long_one], room=100, limit=2) == [short_one, other]


def test_alias_hits_come_before_the_nearest_within_the_room():
    hit, far_hit, near = stored('hit', ['배']), stored('far', ['성']), stored('near')
    thresholds = ReferenceThresholds(keyword_max_distance=0.5, limit=3)

    chosen = choose([hit, far_hit], {hit.id: 0.2, far_hit.id: 0.9}, [near, hit], thresholds, room=100)

    assert chosen == [hit, near]
