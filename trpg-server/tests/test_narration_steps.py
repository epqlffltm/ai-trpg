# trpg-server/tests/test_narration_steps.py

"""
서술의 입력·출력 단계(#387, app/catalog/steps.py)가 서술의 예산과 길이를 어떻게 정하는지 검증한다. DB 를 쓰지 않는다.

보는 것.
  - 단계는 0~2 다. 단계마다 입력 +8,000, 출력 +1,000 토큰이다. 가격표 이름의 끝이 단계다.
  - 입력 단계: 서술의 입력 예산, 작가의 글의 상한, 지난 기록의 라운드 수와 글자 수, 로어북, 기억, 참고 자료가 는다.
  - 출력 단계: 출력 상한, 장면의 길이 안내, 받는 장면의 상한이 는다. 기본 단계의 글은 그대로다.
  - 모델의 단계마다의 값: 기본 단계를 팔아야 내주고, 고른 단계도 팔아야 고를 수 있다. 파는 단계를 함께 내준다.
"""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from ai_core.fake import FakeCallLog, FakeProvider

from app.assets.models import NarrationStyle
from app.billing.prices import FREE_BOOK, Price, PriceBook, Sale, Tier, narration_code
from app.catalog.offers import OfferedModel, StepPrice, offer, options_of
from app.catalog.steps import (
    ALL_STEPS,
    BASE_STEPS,
    NarrationSteps,
    input_tokens,
    output_tokens,
    scaled_chars,
    scaled_count,
    steps_code,
    steps_of,
)
from app.lore.retrieval import LORE_MAX_CHARS, lore_max_chars
from app.memory.retrieval import MemoryThresholds, for_steps
from app.references.retrieval import REFERENCE_MAX_CHARS, room_for
from app.rounds import prompt
from app.rounds.budget import fit_request, input_budget, story_fits
from app.rounds.llm_narrator import LLMNarrator, accept_scene, scene_max_length
from app.rounds.narrator import LoreNote, Move, NarrationRequest, PastRound, StoryContext
from tests.test_model_offers import card

NOW = datetime(2026, 10, 23, 3, 0, tzinfo=UTC)
LONGEST = NarrationSteps(2, 2)
STORY = StoryContext(title='추격전', rating='all', guide='추격은 언제나 바이크로 한다.')


def request_with(steps: NarrationSteps = BASE_STEPS, **changes) -> NarrationRequest:
    base = NarrationRequest(
        round_number=12, scene='사이렌이 가까워진다.', moves=[Move('엘프', '달린다.')], story=STORY, steps=steps
    )
    return replace(base, **changes)


def past(number: int, size: int = 100) -> PastRound:
    return PastRound(number=number, scene='가' * size, lines=['엘프: 달린다.'])


# --- 단계 ---


@pytest.mark.parametrize(('input_step', 'output_step'), [(3, 0), (0, 3), (-1, 0)])
def test_a_step_is_from_zero_to_two(input_step: int, output_step: int):
    with pytest.raises(ValueError):
        NarrationSteps(input_step, output_step)


def test_there_are_nine_steps_starting_from_the_base():
    assert len(ALL_STEPS) == 9
    assert ALL_STEPS[0] == BASE_STEPS
    assert ALL_STEPS[-1] == LONGEST


@pytest.mark.parametrize(
    ('step', 'tokens_in', 'tokens_out'), [(0, 12_000, 1_200), (1, 20_000, 2_200), (2, 28_000, 3_200)]
)
def test_each_step_adds_eight_thousand_in_and_one_thousand_out(step: int, tokens_in: int, tokens_out: int):
    steps = NarrationSteps(step, step)

    assert (input_tokens(steps), output_tokens(steps)) == (tokens_in, tokens_out)


def test_the_caps_grow_with_the_input_step():
    assert [scaled_chars(3000, NarrationSteps(step, 0)) for step in range(3)] == [3000, 5000, 7000]
    assert [scaled_count(3, NarrationSteps(step, 0)) for step in range(3)] == [3, 6, 9]


def test_the_price_code_ends_with_the_steps():
    assert steps_code(NarrationSteps(1, 2)) == 'i1.o2'
    assert narration_code('gpt-6-luna', NarrationSteps(1, 2)) == 'narration.gpt-6-luna.i1.o2'
    assert narration_code('gpt-6-luna') == 'narration.gpt-6-luna.i0.o0'


def test_a_table_or_round_gives_its_steps():
    assert steps_of(SimpleNamespace(input_step=2, output_step=1)) == NarrationSteps(2, 1)


# --- 입력 단계 ---


def test_the_input_budget_is_seventy_percent_of_the_step():
    assert [input_budget(NarrationSteps(step, 0)) for step in range(3)] == [8_400, 14_000, 19_600]


def test_more_history_goes_in_on_a_higher_input_step():
    history = [past(number) for number in range(1, 12)]

    def history_count(steps: NarrationSteps) -> int:
        messages = prompt.build_messages(request_with(steps, history=history))
        return sum(1 for message in messages if message.content.startswith('가'))

    assert [history_count(NarrationSteps(step, 0)) for step in range(3)] == [3, 6, 9]


def test_a_higher_input_step_keeps_more_of_the_history():
    history = [past(number, size=1_900) for number in range(5, 12)]
    request = request_with(NarrationSteps(2, 0), history=history)

    # 기본 단계는 지난 기록 6,000자(셋)까지, 가장 높은 단계는 14,000자(일곱 모두)까지 보낸다
    assert len(fit_request(replace(request, steps=BASE_STEPS)).history) == 3
    assert fit_request(request).history == history


def test_a_long_story_fits_only_a_higher_input_step():
    long = replace(STORY, guide='가' * 15_000)

    assert not story_fits(long, NarrationStyle.NONE, BASE_STEPS)
    assert story_fits(long, NarrationStyle.NONE, NarrationSteps(1, 0))


def test_the_lore_memory_and_references_grow_with_the_input_step():
    steps = NarrationSteps(2, 0)
    lore = [LoreNote(entry_id=uuid.uuid4(), name='드워프', content='가' * 3_997)]

    assert lore_max_chars(BASE_STEPS) == LORE_MAX_CHARS
    assert lore_max_chars(steps) == 7_000
    assert for_steps(MemoryThresholds(), steps) == replace(MemoryThresholds(), count=6, max_chars=4_666)
    # 로어북이 4,000자를 쓰면 기본 단계에는 자리가 없고, 가장 높은 단계에는 3,000자가 남는다(참고 자료는 3,500 까지)
    assert room_for(request_with(lore=lore)) == 0
    assert room_for(request_with(steps, lore=lore)) == 3_000
    assert room_for(request_with(steps)) == scaled_chars(REFERENCE_MAX_CHARS, steps)


# --- 출력 단계 ---


def test_the_base_step_keeps_the_old_scene_length():
    assert prompt.GM_RULES.endswith('600~900자 안팎이면 충분하다. 길어도 1,200자를 넘기지 마라.')


@pytest.mark.parametrize(
    ('step', 'line'),
    [
        (1, '1,100~1,600자 안팎이면 충분하다. 길어도 2,000자를'),
        (2, '1,600~2,400자 안팎이면 충분하다. 길어도 2,800자를'),
    ],
)
def test_a_higher_output_step_asks_for_a_longer_scene(step: int, line: str):
    system = prompt.system_text(STORY, NarrationStyle.NONE, NarrationSteps(0, step))

    assert line in system
    assert '1,200자를 넘기지' not in system


def test_the_scene_limit_grows_with_the_output_step():
    assert [scene_max_length(NarrationSteps(0, step)) for step in range(3)] == [4_000, 7_000, 10_000]
    assert accept_scene('가' * 9_000, scene_max_length(LONGEST)) == '가' * 9_000


@pytest.mark.parametrize('step', [0, 1, 2])
async def test_the_narrator_asks_for_the_output_of_its_step(step: int):
    provider = FakeProvider(reply='문이 열렸다.')
    log = FakeCallLog()
    narrator = LLMNarrator(provider, log)

    await narrator.narrate(request_with(NarrationSteps(0, step)))

    (call,) = provider.calls
    assert call.params.max_tokens == output_tokens(NarrationSteps(0, step))
    assert log.records[0].max_tokens == call.params.max_tokens


async def test_a_long_scene_is_taken_only_on_a_higher_output_step():
    provider = FakeProvider(reply='가' * 6_000)

    scene = await LLMNarrator(provider, FakeCallLog()).narrate(request_with(NarrationSteps(0, 1)))

    assert len(scene) == 6_000


# --- 단계마다의 값 ---


def sold(slug: str, steps: NarrationSteps, credits: str) -> Price:
    return Price(code=narration_code(slug, steps), current=Sale(credits, Tier.STANDARD))


def test_a_model_is_offered_at_a_step_only_when_both_are_sold():
    higher = NarrationSteps(1, 0)
    only_higher = PriceBook(prices={price.code: price for price in [sold('gpt-6-luna', higher, '40')]})
    both = PriceBook(
        prices={price.code: price for price in [sold('gpt-6-luna', BASE_STEPS, '20'), sold('gpt-6-luna', higher, '40')]}
    )

    assert offer(card(), only_higher, NOW, higher) is None
    assert offer(card(), both, NOW, NarrationSteps(2, 0)) is None
    found = offer(card(), both, NOW, higher)
    assert (found.credits, found.steps) == ('40', higher)


def test_the_options_are_the_sold_steps_in_order():
    steps = [NarrationSteps(0, 1), BASE_STEPS, NarrationSteps(1, 0)]
    prices = PriceBook(prices={price.code: price for price in [sold('gpt-6-luna', item, '20') for item in steps]})

    options = options_of('gpt-6-luna', prices, NOW)

    assert [option.steps for option in options] == [BASE_STEPS, NarrationSteps(0, 1), NarrationSteps(1, 0)]


def test_without_a_billing_server_every_step_is_offered_free():
    options = options_of('gpt-6-luna', FREE_BOOK, NOW)

    assert options == tuple(StepPrice(steps, None, None) for steps in ALL_STEPS)
    assert offer(card(), FREE_BOOK, NOW, LONGEST) == OfferedModel(
        'gpt-6-luna', 'GPT-6 Luna', 'openai', card().grade, None, None, steps=LONGEST
    )
