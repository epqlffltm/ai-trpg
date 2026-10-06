# game-server/tests/test_narrator.py

"""
가짜 서술자를 검증한다. DB 를 쓰지 않는다.

가짜 서술자는 AI 가 붙기 전에 라운드의 흐름을 돌려 보는 데 쓴다. 같은 입력에 늘 같은 글을 내야 테스트에 쓸 수 있다.
"""

from app.rounds.narrator import FakeNarrator, Impact, Move, NarrationRequest, Verdict, describe_impact, describe_verdict


def make_request(moves: list[Move]) -> NarrationRequest:
    return NarrationRequest(round_number=3, scene='사이렌이 울린다.', moves=moves)


def make_verdict(**overrides) -> Verdict:
    """근력으로 어려움에 도전해 13 이 나온 판정. 보정 2 를 더해 15, 목표 20 이라 실패다."""
    values = {
        'ability': '근력',
        'difficulty': '어려움',
        'roll': 13,
        'modifier': 2,
        'total': 15,
        'target': 20,
        'success': False,
    }
    return Verdict(**{**values, **overrides})


async def test_lists_every_move_in_order():
    request = make_request([Move('폭주족 엘프', '바이크에 시동을 건다.'), Move('악역영애', '크게 웃는다.')])

    narration = await FakeNarrator().narrate(request)

    assert narration == '[3 라운드의 결과]\n폭주족 엘프: 바이크에 시동을 건다.\n악역영애: 크게 웃는다.'


async def test_a_character_without_a_declaration_does_nothing():
    request = make_request([Move('폭주족 엘프', None)])

    narration = await FakeNarrator().narrate(request)

    assert narration == '[3 라운드의 결과]\n폭주족 엘프: 아무것도 하지 않았다.'


async def test_the_same_request_gives_the_same_narration():
    request = make_request([Move('폭주족 엘프', '달린다.')])

    assert await FakeNarrator().narrate(request) == await FakeNarrator().narrate(request)


# --- 판정의 결과 ---


async def test_a_verdict_follows_the_move_it_belongs_to():
    request = make_request([Move('폭주족 엘프', '문을 걷어찬다.', make_verdict()), Move('악역영애', '크게 웃는다.')])

    narration = await FakeNarrator().narrate(request)

    assert narration == (
        '[3 라운드의 결과]\n폭주족 엘프: 문을 걷어찬다. (근력 판정 실패: 13 + 2 = 15, 목표 20)\n악역영애: 크게 웃는다.'
    )


def test_a_success_is_written_as_a_success():
    verdict = make_verdict(roll=18, total=20, success=True)

    assert describe_verdict(verdict) == '(근력 판정 성공: 18 + 2 = 20, 목표 20)'


def test_a_negative_modifier_is_written_as_a_subtraction():
    verdict = make_verdict(modifier=-1, total=12)

    assert describe_verdict(verdict) == '(근력 판정 실패: 13 - 1 = 12, 목표 20)'


def test_a_zero_modifier_is_written_as_plus_zero():
    verdict = make_verdict(modifier=0, total=13)

    assert describe_verdict(verdict) == '(근력 판정 실패: 13 + 0 = 13, 목표 20)'


# --- HP 의 변화 ---


def make_impact(**overrides) -> Impact:
    """엘프가 피해 3 을 입어 HP 가 7 이 된 것."""
    values = {'kind': 'damage', 'character_name': '폭주족 엘프', 'amount': 3, 'hp': 7, 'max_hp': 10, 'downed': False}
    return Impact(**{**values, **overrides})


def test_damage_is_written_with_the_hp_left():
    assert describe_impact(make_impact()) == '→ 폭주족 엘프 피해 3 (HP 7/10)'


def test_recovery_is_written_with_the_one_who_recovered():
    impact = make_impact(kind='recovery', character_name='악역영애', amount=4, hp=4)

    assert describe_impact(impact) == '→ 악역영애 회복 4 (HP 4/10)'


def test_going_down_is_written():
    assert describe_impact(make_impact(amount=16, hp=0, downed=True)) == '→ 폭주족 엘프 피해 16 (HP 0/10, 쓰러짐)'


async def test_an_impact_follows_the_verdict_that_caused_it():
    verdict = make_verdict(impact=make_impact())
    request = make_request([Move('폭주족 엘프', '문을 걷어찬다.', verdict)])

    narration = await FakeNarrator().narrate(request)

    assert narration == (
        '[3 라운드의 결과]\n'
        '폭주족 엘프: 문을 걷어찬다. (근력 판정 실패: 13 + 2 = 15, 목표 20) → 폭주족 엘프 피해 3 (HP 7/10)'
    )


async def test_a_downed_character_without_a_declaration_lies_down():
    request = make_request([Move('폭주족 엘프', None, downed=True), Move('악역영애', None)])

    narration = await FakeNarrator().narrate(request)

    assert narration == '[3 라운드의 결과]\n폭주족 엘프: 쓰러져 있다.\n악역영애: 아무것도 하지 않았다.'


async def test_a_downed_character_can_still_say_something():
    request = make_request([Move('폭주족 엘프', '신음한다.', downed=True)])

    narration = await FakeNarrator().narrate(request)

    assert narration == '[3 라운드의 결과]\n폭주족 엘프: 신음한다.'
