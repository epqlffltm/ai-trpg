# story-server/tests/test_try_scene.py

"""
장면 재기(scripts/try_scene.py)의 세는 함수를 검증한다. 진짜 모델 대신 정해 둔 대로 답하는 가짜(tests/models.py)를 쓴다.
DB 도 앱도 없다.

보는 것.
  - 장면의 인물 수만큼 카드에 인물이 들고, 상한(4명)을 넘는 수도 그대로 든다
  - 답을 장면의 인물로 센다: 말한 인물, 말 없는 인물, 장면에 없는 인물의 줄(버림), 서술의 수
  - 이벤트의 장면과 선택지의 반응을 차례로 부르고, 둘째 호출에 첫 답과 고른 것이 들어간다. 원가는 단가가 있을 때만 센다
  - 첫 호출이 실패하면 둘째는 부르지 않는다
"""

from decimal import Decimal

from ai_core.provider import ProviderError

from scripts.try_scene import (
    CHOICES,
    cast_line,
    cast_of,
    flow_line,
    run_cast_trial,
    run_flow_trial,
    sample,
    scene_messages,
)
from tests.models import ScriptedProvider


def test_the_card_carries_every_cast_member_even_past_the_limit():
    source = sample()

    card = scene_messages(source, cast_of(6), '', [])[0].content

    assert all(f'@{cast_id} (' in card for cast_id in cast_of(6))
    assert '@rin' not in scene_messages(source, cast_of(4), '', [])[0].content


async def test_an_answer_is_counted_against_the_scene_cast():
    provider = ScriptedProvider(pieces=['@narration: 등불이 켜진다.\n@mina: 와!\n@rin: 저기...\n@jun: 가자.'])

    trial = await run_cast_trial(provider, sample(), 3)

    assert trial.stats is not None
    assert (trial.stats.spoke, trial.stats.silent) == (('mina', 'jun'), ('sora',))
    assert (trial.stats.dropped, trial.stats.lines, trial.stats.narration) == (1, 3, 1)
    assert '2/3' in cast_line(trial)


async def test_the_reaction_sees_the_scene_and_the_choice_and_costs_are_counted():
    provider = ScriptedProvider(pieces=['@hana: 무대로 올라오세요!'], input_tokens=1000, output_tokens=200)

    trial = await run_flow_trial(provider, sample(), Decimal('1'), Decimal('5'))

    second_messages, _ = provider.calls[1]
    assert [message.content for message in second_messages[1:]][-2:] == [
        '@hana: 무대로 올라오세요!',
        f'[행동] 고른 것: {CHOICES[0]}',
    ]
    assert '[장면 지시]' in provider.calls[0][0][0].content
    assert '[장면 지시]' not in second_messages[0].content
    assert trial.costs == (Decimal('0.002'), Decimal('0.002'))
    assert '$0.00400' in flow_line(trial)


async def test_without_prices_or_after_a_failure_nothing_is_guessed():
    unpriced = await run_flow_trial(ScriptedProvider(), sample(), None, None)
    failed = await run_flow_trial(ScriptedProvider(error=ProviderError('down')), sample(), Decimal('1'), Decimal('5'))

    assert unpriced.costs == (None, None)
    assert (failed.reaction, failed.scene.problem) == (None, 'provider 실패: down')
