# game-server/tests/test_narrator.py

"""
가짜 서술자를 검증한다. DB 를 쓰지 않는다.

가짜 서술자는 AI 가 붙기 전에 라운드의 흐름을 돌려 보는 데 쓴다. 같은 입력에 늘 같은 글을 내야 테스트에 쓸 수 있다.
"""

from app.rounds.narrator import Action, FakeNarrator, NarrationRequest


def make_request(actions: list[Action]) -> NarrationRequest:
    return NarrationRequest(round_number=3, scene='사이렌이 울린다.', actions=actions)


async def test_lists_every_action_in_order():
    request = make_request([Action('폭주족 엘프', '바이크에 시동을 건다.'), Action('악역영애', '크게 웃는다.')])

    narration = await FakeNarrator().narrate(request)

    assert narration == '[3 라운드의 결과]\n폭주족 엘프: 바이크에 시동을 건다.\n악역영애: 크게 웃는다.'


async def test_a_character_without_a_declaration_does_nothing():
    request = make_request([Action('폭주족 엘프', None)])

    narration = await FakeNarrator().narrate(request)

    assert narration == '[3 라운드의 결과]\n폭주족 엘프: 아무것도 하지 않았다.'


async def test_the_same_request_gives_the_same_narration():
    request = make_request([Action('폭주족 엘프', '달린다.')])

    assert await FakeNarrator().narrate(request) == await FakeNarrator().narrate(request)
