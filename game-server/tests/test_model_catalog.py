# game-server/tests/test_model_catalog.py

"""
모델 목록(app/catalog)을 검증한다. 관리 명령(scripts/models.py)은 tests/test_models_script.py 가 본다.

"오늘"은 테스트가 정한다. 실제 시계를 읽지 않는다.

다섯을 본다.
  - 모양: 이름표, 출력 상한의 칸과 창구, 바꿀 것, 단가(app/catalog/schemas.py).
  - 판단: 은퇴, 쓸 수 있나, 1라운드 원가 어림(app/catalog/rules.py).
  - 모델: 넣기(꺼진 채로, 겹치면 거절), 바꾸기(적은 것만), 켜기(원가가 있고 은퇴하지 않아야), 끄기, 은퇴일.
  - 원가: 덧붙이기만 한다. 그날의 단가는 그날 이전에 시작한 것 중 가장 늦은 것, 같은 날이면 나중에 적은 것이다.
  - 날짜판: 따로 둔 일로만 바꾼다. 바꾸면 기록이 남고 모델이 꺼진다. 이름표와 값은 그대로다.
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import repository, service
from app.catalog.errors import CatalogConflictError, Conflict, InvalidModelError, ModelNotFoundError
from app.catalog.models import AiModel, AiModelCost, Grade, Provider, ReasoningStyle, TokenLimitField
from app.catalog.rules import always_thinks, is_offered, is_retired, round_cost_usd
from app.catalog.schemas import SLUG_MAX_LENGTH, CostCreate, ModelCreate, ModelUpdate, SnapshotSwitch

pytestmark = pytest.mark.usefixtures('empty_catalog')

TODAY = date(2026, 10, 17)

# 이 테스트의 모델. API 모델 이름은 지어낸 것이다
LUNA = ModelCreate(
    slug='gpt-6-luna',
    provider=Provider.OPENAI,
    api_model_id='gpt-6-luna-2026-09-22',
    display_name='GPT-6 Luna',
    vendor='openai',
    grade=Grade.STANDARD,
    supports_reasoning=True,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
)
OPUS = ModelCreate(
    slug='claude-opus-5-5',
    provider=Provider.ANTHROPIC,
    api_model_id='claude-opus-5-5-20260901',
    display_name='Claude Opus 5.5',
    vendor='anthropic',
    grade=Grade.PREMIUM,
    supports_temperature=False,
    reasoning_style=ReasoningStyle.ALWAYS,
)


def cost(input_price: str = '0.1', output_price: str = '0.5', starts: date = TODAY, **extra) -> CostCreate:
    """단가 하나. 확인한 날은 오늘이다."""
    return CostCreate(
        input_per_mtok=Decimal(input_price),
        output_per_mtok=Decimal(output_price),
        effective_from=starts,
        checked_on=TODAY,
        **extra,
    )


def luna_with(**changes) -> ModelCreate:
    """LUNA 에서 몇 칸만 바꾼 것."""
    return LUNA.model_copy(update=changes)


async def fresh_model(session: AsyncSession, slug: str) -> AiModel:
    """DB 에 저장된 모델을 새로 읽는다."""
    session.expire_all()
    return await session.scalar(select(AiModel).where(AiModel.slug == slug))


# --- 모양 ---


@pytest.mark.parametrize('slug', ['gpt-6-luna', 'gemini-4-argon', 'kimi-k3', 'a' * SLUG_MAX_LENGTH])
def test_slugs_are_lowercase_words_joined_by_hyphens(slug: str):
    assert ModelCreate(**{**LUNA.model_dump(), 'slug': slug}).slug == slug


@pytest.mark.parametrize('slug', ['gpt-5.6-sol', 'GPT-6', 'gpt_6', '-gpt', 'gpt--6', '', 'a' * (SLUG_MAX_LENGTH + 1)])
def test_other_slugs_are_refused(slug: str):
    # 점은 결제 서버의 가격 코드(narration.<이름표>.i0.o0)에서 칸을 나눈다
    with pytest.raises(ValidationError):
        ModelCreate(**{**LUNA.model_dump(), 'slug': slug})


def test_an_openai_model_needs_its_token_field():
    with pytest.raises(ValidationError, match='출력 상한의 칸'):
        ModelCreate(**{**LUNA.model_dump(), 'token_limit_field': None})


def test_a_claude_model_takes_no_token_field():
    with pytest.raises(ValidationError, match='적지 않는다'):
        ModelCreate(**{**OPUS.model_dump(), 'token_limit_field': TokenLimitField.MAX_TOKENS})


def test_a_claude_model_needs_its_reasoning_style():
    with pytest.raises(ValidationError, match='생각을 켜고 끄는 방식'):
        ModelCreate(**{**OPUS.model_dump(), 'reasoning_style': None})


def test_an_openai_model_takes_no_reasoning_style():
    with pytest.raises(ValidationError, match='적지 않는다'):
        ModelCreate(**{**LUNA.model_dump(), 'reasoning_style': ReasoningStyle.ADAPTIVE})


def test_a_gemini_model_takes_only_the_gemini_styles():
    gemini = {
        **OPUS.model_dump(),
        'slug': 'gemini-4-argon',
        'provider': Provider.GEMINI,
        'api_model_id': 'gemini-4-argon',
    }

    assert ModelCreate(**{**gemini, 'reasoning_style': ReasoningStyle.LEVEL_LOW}).reasoning_style == 'level_low'
    # adaptive 는 Claude 의 방식이다
    with pytest.raises(ValidationError, match='받는 생각의 방식이 아니다'):
        ModelCreate(**{**gemini, 'reasoning_style': ReasoningStyle.ADAPTIVE})


def test_a_claude_model_takes_only_the_claude_styles():
    with pytest.raises(ValidationError, match='받는 생각의 방식이 아니다'):
        ModelCreate(**{**OPUS.model_dump(), 'reasoning_style': ReasoningStyle.LEVEL_MINIMAL})


@pytest.mark.parametrize(
    ('style', 'always'),
    [
        (ReasoningStyle.ALWAYS, True),
        (ReasoningStyle.LEVEL_MINIMAL, True),
        (ReasoningStyle.LEVEL_LOW, True),
        (ReasoningStyle.BUDGET_MIN, True),
        (ReasoningStyle.ADAPTIVE, False),
        (ReasoningStyle.BETWEEN_TOOLS, False),
        (ReasoningStyle.BUDGET, False),
        (None, False),
    ],
)
def test_the_styles_that_cannot_stop_thinking(style: ReasoningStyle | None, always: bool):
    # 이 모델들은 판매가와 출력 상한에 생각의 몫을 넣는다
    assert always_thinks(style) is always


def test_api_model_ids_have_no_spaces():
    with pytest.raises(ValidationError):
        ModelCreate(**{**LUNA.model_dump(), 'api_model_id': 'gpt 6'})


def test_unknown_providers_are_refused():
    with pytest.raises(ValidationError):
        ModelCreate(**{**LUNA.model_dump(), 'provider': 'bedrock'})


def test_an_update_needs_something_to_change():
    with pytest.raises(ValidationError, match='바꿀 것이 없다'):
        ModelUpdate()


def test_an_update_carries_only_what_was_given():
    assert ModelUpdate(grade=Grade.PREMIUM, supports_temperature=False).changes() == {
        'grade': Grade.PREMIUM,
        'supports_temperature': False,
    }


def test_prices_are_not_negative():
    with pytest.raises(ValidationError):
        cost(input_price='-0.1')


def test_a_cached_input_dearer_than_the_input_is_refused():
    with pytest.raises(ValidationError, match='캐시 읽기'):
        cost(input_price='1', cached_input_per_mtok=Decimal('2'))


def test_prices_keep_six_decimal_places():
    assert cost(input_price='0.075').input_per_mtok == Decimal('0.075')
    with pytest.raises(ValidationError):
        cost(input_price='0.0000001')


# --- 판단 ---


def model_row(enabled: bool = True, retires_on: date | None = None) -> AiModel:
    """DB 에 넣지 않은 모델 한 줄."""
    return AiModel(**LUNA.model_dump(), enabled=enabled, retires_on=retires_on)


def test_a_model_retires_on_its_retirement_day():
    model = model_row(retires_on=TODAY)

    assert is_retired(model, TODAY)
    assert not is_retired(model, TODAY - timedelta(days=1))


def test_a_model_without_a_retirement_day_never_retires():
    assert not is_retired(model_row(), date(2099, 1, 1))


@pytest.mark.parametrize(
    ('enabled', 'retires_on', 'offered'),
    [(True, None, True), (False, None, False), (True, TODAY, False), (True, TODAY + timedelta(days=1), True)],
)
def test_a_model_is_offered_when_enabled_and_not_retired(enabled: bool, retires_on: date | None, offered: bool):
    assert is_offered(model_row(enabled, retires_on), TODAY) is offered


def test_a_round_costs_twelve_thousand_inputs_and_twelve_hundred_outputs():
    # GPT-6 Luna: $0.1/$0.5 → 0.0012 + 0.0006. 1500원이면 2.7원이다(model-pricing-plan 의 표와 같다)
    row = AiModelCost(input_per_mtok=Decimal('0.1'), output_per_mtok=Decimal('0.5'))

    assert round_cost_usd(row) == Decimal('0.0018')


# --- 모델 ---


async def test_a_new_model_starts_disabled(session: AsyncSession):
    await service.add_model(session, LUNA)

    model = await fresh_model(session, 'gpt-6-luna')
    assert (model.enabled, model.api_model_id, model.grade, model.token_limit_field) == (
        False,
        'gpt-6-luna-2026-09-22',
        'standard',
        'max_completion_tokens',
    )
    assert (model.supports_reasoning, model.supports_temperature, model.retires_on) == (True, True, None)


async def test_a_taken_slug_is_refused(session: AsyncSession):
    await service.add_model(session, LUNA)

    with pytest.raises(CatalogConflictError) as caught:
        await service.add_model(session, luna_with(api_model_id='gpt-6-luna-2026-12-01'))
    assert caught.value.reason == Conflict.SLUG_TAKEN


async def test_the_same_api_model_under_another_slug_is_refused(session: AsyncSession):
    await service.add_model(session, LUNA)

    with pytest.raises(CatalogConflictError) as caught:
        await service.add_model(session, luna_with(slug='luna-again'))
    assert caught.value.reason == Conflict.API_MODEL_TAKEN


async def test_the_same_api_model_id_on_another_provider_is_a_different_model(session: AsyncSession):
    await service.add_model(session, LUNA)

    await service.add_model(session, luna_with(slug='luna-local', provider=Provider.LOCAL, grade=Grade.BASIC))

    assert len(await repository.list_models(session)) == 2


async def test_an_update_changes_only_what_was_given(session: AsyncSession):
    await service.add_model(session, LUNA)

    await service.update_model(session, 'gpt-6-luna', ModelUpdate(supports_temperature=False, display_name='루나'))

    model = await fresh_model(session, 'gpt-6-luna')
    assert (model.supports_temperature, model.display_name, model.grade, model.supports_reasoning) == (
        False,
        '루나',
        'standard',
        True,
    )


async def test_a_token_field_cannot_be_given_to_a_claude_model(session: AsyncSession):
    await service.add_model(session, OPUS)

    with pytest.raises(InvalidModelError, match='적지 않는다'):
        await service.update_model(
            session, 'claude-opus-5-5', ModelUpdate(token_limit_field=TokenLimitField.MAX_TOKENS)
        )


async def test_a_reasoning_style_cannot_be_given_to_an_openai_model(session: AsyncSession):
    await service.add_model(session, LUNA)

    with pytest.raises(InvalidModelError, match='생각을 켜고 끄는 방식을 적지 않는다'):
        await service.update_model(session, 'gpt-6-luna', ModelUpdate(reasoning_style=ReasoningStyle.ADAPTIVE))


async def test_the_reasoning_style_of_a_claude_model_can_be_changed(session: AsyncSession):
    await service.add_model(session, OPUS)

    await service.update_model(session, 'claude-opus-5-5', ModelUpdate(reasoning_style=ReasoningStyle.ADAPTIVE))

    assert (await fresh_model(session, 'claude-opus-5-5')).reasoning_style == 'adaptive'


async def test_unknown_models_are_not_found(session: AsyncSession):
    with pytest.raises(ModelNotFoundError):
        await service.update_model(session, 'nothing', ModelUpdate(grade=Grade.PREMIUM))
    with pytest.raises(ModelNotFoundError):
        await service.add_cost(session, 'nothing', cost())
    with pytest.raises(ModelNotFoundError):
        await service.enable_model(session, 'nothing', TODAY)


async def test_a_model_without_a_cost_cannot_be_enabled(session: AsyncSession):
    await service.add_model(session, LUNA)

    with pytest.raises(CatalogConflictError) as caught:
        await service.enable_model(session, 'gpt-6-luna', TODAY)
    assert caught.value.reason == Conflict.NO_COST


async def test_a_cost_that_starts_later_does_not_count_for_enabling(session: AsyncSession):
    await service.add_model(session, LUNA)
    await service.add_cost(session, 'gpt-6-luna', cost(starts=TODAY + timedelta(days=1)))

    with pytest.raises(CatalogConflictError):
        await service.enable_model(session, 'gpt-6-luna', TODAY)


async def test_a_model_with_a_cost_can_be_enabled_and_disabled(session: AsyncSession):
    await service.add_model(session, LUNA)
    await service.add_cost(session, 'gpt-6-luna', cost())

    await service.enable_model(session, 'gpt-6-luna', TODAY)
    assert (await fresh_model(session, 'gpt-6-luna')).enabled

    await service.disable_model(session, 'gpt-6-luna')
    assert not (await fresh_model(session, 'gpt-6-luna')).enabled


async def test_a_retired_model_cannot_be_enabled(session: AsyncSession):
    await service.add_model(session, LUNA)
    await service.add_cost(session, 'gpt-6-luna', cost())
    await service.retire_model(session, 'gpt-6-luna', TODAY)

    with pytest.raises(CatalogConflictError) as caught:
        await service.enable_model(session, 'gpt-6-luna', TODAY)
    assert caught.value.reason == Conflict.RETIRED


async def test_a_retirement_day_can_be_set_and_cancelled(session: AsyncSession):
    await service.add_model(session, LUNA)

    await service.retire_model(session, 'gpt-6-luna', date(2027, 6, 1))
    assert (await fresh_model(session, 'gpt-6-luna')).retires_on == date(2027, 6, 1)

    await service.retire_model(session, 'gpt-6-luna', None)
    assert (await fresh_model(session, 'gpt-6-luna')).retires_on is None


# --- 원가 ---


async def test_costs_are_appended_and_all_kept(session: AsyncSession):
    await service.add_model(session, LUNA)
    await service.add_cost(session, 'gpt-6-luna', cost('0.1', '0.5', TODAY - timedelta(days=30)))
    await service.add_cost(session, 'gpt-6-luna', cost('0.2', '1', TODAY, note='값을 올렸다'))

    detail = await service.show_model(session, 'gpt-6-luna')

    # 늦게 시작하는 것부터
    assert [(row.input_per_mtok, row.note) for row in detail.costs] == [
        (Decimal('0.2'), '값을 올렸다'),
        (Decimal('0.1'), None),
    ]


async def test_the_cost_of_a_day_is_the_latest_that_started(session: AsyncSession):
    await service.add_model(session, LUNA)
    # GPT-5.6 Sol 처럼 행사가 끝나는 날의 값을 미리 적어 둔다
    await service.add_cost(session, 'gpt-6-luna', cost('4', '20', date(2026, 10, 1)))
    await service.add_cost(session, 'gpt-6-luna', cost('5', '30', date(2026, 11, 21)))

    before = await repository.cost_on(session, 'gpt-6-luna', date(2026, 11, 20))
    after = await repository.cost_on(session, 'gpt-6-luna', date(2026, 11, 21))

    assert (before.input_per_mtok, after.input_per_mtok) == (Decimal('4'), Decimal('5'))
    assert await repository.cost_on(session, 'gpt-6-luna', date(2026, 9, 30)) is None


async def test_a_correction_on_the_same_day_wins(session: AsyncSession):
    await service.add_model(session, LUNA)
    await service.add_cost(session, 'gpt-6-luna', cost('1', '5'))
    await service.add_cost(session, 'gpt-6-luna', cost('0.1', '0.5', note='잘못 적은 것을 고친다'))

    current = await repository.cost_on(session, 'gpt-6-luna', TODAY)

    assert current.input_per_mtok == Decimal('0.1')


async def test_the_list_shows_each_model_with_the_cost_of_the_day(session: AsyncSession):
    await service.add_model(session, LUNA)
    await service.add_model(session, OPUS)
    await service.add_cost(session, 'gpt-6-luna', cost('0.1', '0.5', TODAY - timedelta(days=1)))
    await service.add_cost(session, 'gpt-6-luna', cost('0.2', '1', TODAY + timedelta(days=1)))

    entries = await service.list_entries(session, TODAY)

    # 회사 순서다. Opus 에는 단가가 없다
    assert [(entry.model.slug, entry.cost and entry.cost.input_per_mtok) for entry in entries] == [
        ('claude-opus-5-5', None),
        ('gpt-6-luna', Decimal('0.1')),
    ]


async def test_cache_prices_are_kept(session: AsyncSession):
    await service.add_model(session, OPUS)

    await service.add_cost(
        session,
        'claude-opus-5-5',
        cost('4', '20', cached_input_per_mtok=Decimal('0.4'), cache_write_per_mtok=Decimal('5')),
    )

    current = await repository.cost_on(session, 'claude-opus-5-5', TODAY)
    assert (current.cached_input_per_mtok, current.cache_write_per_mtok) == (Decimal('0.4'), Decimal('5'))


# --- 날짜판 ---

NEXT_LUNA = 'gpt-6-luna-2026-12-01'


async def enabled_luna(session: AsyncSession) -> None:
    """원가를 적고 켠 LUNA."""
    await service.add_model(session, LUNA)
    await service.add_cost(session, 'gpt-6-luna', cost())
    await service.enable_model(session, 'gpt-6-luna', TODAY)


def test_an_update_cannot_change_the_snapshot():
    # 날짜판은 SnapshotSwitch 로만 바꾼다
    with pytest.raises(ValidationError):
        ModelUpdate(api_model_id=NEXT_LUNA)


async def test_switching_the_snapshot_keeps_the_slug_and_disables_the_model(session: AsyncSession):
    await enabled_luna(session)

    await service.switch_snapshot(session, 'gpt-6-luna', SnapshotSwitch(api_model_id=NEXT_LUNA, note='공지'))

    model = await fresh_model(session, 'gpt-6-luna')
    assert (model.api_model_id, model.enabled) == (NEXT_LUNA, False)
    # 같은 상품이라 값은 그대로다. 평가를 다시 통과하면 그대로 켤 수 있다
    await service.enable_model(session, 'gpt-6-luna', TODAY)


async def test_a_switch_is_recorded(session: AsyncSession):
    await enabled_luna(session)
    await service.switch_snapshot(session, 'gpt-6-luna', SnapshotSwitch(api_model_id=NEXT_LUNA, note='공지'))
    await service.switch_snapshot(session, 'gpt-6-luna', SnapshotSwitch(api_model_id='gpt-6-luna-2027-03-01'))

    detail = await service.show_model(session, 'gpt-6-luna')

    # 나중에 바꾼 것부터
    assert [(row.previous_api_model_id, row.api_model_id, row.note) for row in detail.snapshots] == [
        (NEXT_LUNA, 'gpt-6-luna-2027-03-01', None),
        ('gpt-6-luna-2026-09-22', NEXT_LUNA, '공지'),
    ]


async def test_switching_to_the_same_snapshot_is_refused(session: AsyncSession):
    await service.add_model(session, LUNA)

    with pytest.raises(CatalogConflictError) as caught:
        await service.switch_snapshot(session, 'gpt-6-luna', SnapshotSwitch(api_model_id=LUNA.api_model_id))
    assert caught.value.reason == Conflict.SAME_SNAPSHOT
    assert (await service.show_model(session, 'gpt-6-luna')).snapshots == []


async def test_switching_to_a_snapshot_another_model_uses_is_refused(session: AsyncSession):
    await service.add_model(session, LUNA)
    await service.add_model(session, luna_with(slug='gpt-6-luna-mini', api_model_id=NEXT_LUNA))

    with pytest.raises(CatalogConflictError) as caught:
        await service.switch_snapshot(session, 'gpt-6-luna', SnapshotSwitch(api_model_id=NEXT_LUNA))
    assert caught.value.reason == Conflict.API_MODEL_TAKEN


async def test_switching_an_unknown_model_is_not_found(session: AsyncSession):
    with pytest.raises(ModelNotFoundError):
        await service.switch_snapshot(session, 'nothing', SnapshotSwitch(api_model_id=NEXT_LUNA))


async def test_switches_at_the_same_time_keep_the_chain(app, session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    await service.add_model(session, LUNA)
    checked = service.require_new_snapshot

    async def slow_check(*args) -> None:
        # 읽고 나서 잠깐 쉰다. 잠그지 않으면 그사이에 다른 쪽도 옛 이름을 읽는다
        await checked(*args)
        await asyncio.sleep(0.05)

    monkeypatch.setattr(service, 'require_new_snapshot', slow_check)

    async def switch(api_model_id: str) -> None:
        async with app.state.session_factory() as own:
            await service.switch_snapshot(own, 'gpt-6-luna', SnapshotSwitch(api_model_id=api_model_id))

    await asyncio.gather(switch(NEXT_LUNA), switch('gpt-6-luna-2027-03-01'))

    # 모델의 줄을 잠그므로 뒤에 바꾼 쪽은 앞에서 바꾼 이름을 "앞의 이름"으로 적는다
    detail = await service.show_model(session, 'gpt-6-luna')
    later, earlier = detail.snapshots
    assert earlier.previous_api_model_id == LUNA.api_model_id
    assert later.previous_api_model_id == earlier.api_model_id
    assert detail.model.api_model_id == later.api_model_id
