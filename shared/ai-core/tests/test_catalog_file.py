# shared/ai-core/tests/test_catalog_file.py

"""
모델 목록의 원본 파일(ai_core/model_catalog.toml)과 그것을 읽는 것(ai_core/catalog_file.py)을 검증한다.

보는 것.
  - 모양: 이름표, API 모델 이름, 창구에 맞는 출력 상한의 칸과 생각의 방식, 분류, 단가(음수, 자릿수, 캐시 읽기)
  - 파일: 판(format), TOML 이 아닌 것, 모르는 칸, 겹치는 이름표와 API 모델, 한 모델의 같은 날 단가 둘
  - 값: 단가를 Decimal 로 읽는다(float 로 틀어지지 않는다). 날짜는 날짜다
  - 저장소의 파일: 읽히고, 이름표가 가격 코드에 맞고, 은퇴일과 단가가 말이 된다
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_core.catalog_contract import Grade, Provider, ReasoningStyle, TokenLimitField
from ai_core.catalog_file import (
    FORMAT,
    SLUG_MAX_LENGTH,
    CatalogFileError,
    CostEntry,
    ModelCatalog,
    ModelEntry,
    load_catalog,
    parse_catalog,
)

TODAY = date(2026, 10, 17)

# 이 테스트의 모델. API 모델 이름은 지어낸 것이다
LUNA = ModelEntry(
    slug='gpt-6-luna',
    provider=Provider.OPENAI,
    api_model_id='gpt-6-luna-2026-09-22',
    display_name='GPT-6 Luna',
    vendor='openai',
    grade=Grade.STANDARD,
    supports_reasoning=True,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
)
OPUS = ModelEntry(
    slug='claude-opus-5-5',
    provider=Provider.ANTHROPIC,
    api_model_id='claude-opus-5-5-20260901',
    display_name='Claude Opus 5.5',
    vendor='anthropic',
    grade=Grade.PREMIUM,
    supports_temperature=False,
    reasoning_style=ReasoningStyle.ALWAYS,
)
LUNA_TOML = """
format = 1

[[models]]
slug = "gpt-6-luna"
provider = "openai"
api_model_id = "gpt-6-luna-2026-09-22"
display_name = "GPT-6 Luna"
vendor = "openai"
grade = "standard"
supports_reasoning = true
token_limit_field = "max_completion_tokens"
retires_on = 2027-06-01

[[models.costs]]
effective_from = 2026-10-17
checked_on = 2026-10-17
input_per_mtok = 0.1
cached_input_per_mtok = 0.01
output_per_mtok = 0.5
"""


def with_fields(model: ModelEntry, **changes) -> ModelEntry:
    """몇 칸만 바꾼 모델. 모양을 다시 본다."""
    return ModelEntry(**{**model.model_dump(), **changes})


def cost(input_price: str = '0.1', starts: date = TODAY, **extra) -> CostEntry:
    """단가 하나. 출력은 0.5 다."""
    return CostEntry(
        input_per_mtok=Decimal(input_price),
        output_per_mtok=Decimal('0.5'),
        effective_from=starts,
        checked_on=TODAY,
        **extra,
    )


# --- 모양 ---


@pytest.mark.parametrize('slug', ['gpt-6-luna', 'gemini-4-argon', 'kimi-k3', 'a' * SLUG_MAX_LENGTH])
def test_slugs_are_lowercase_words_joined_by_hyphens(slug: str):
    assert with_fields(LUNA, slug=slug).slug == slug


@pytest.mark.parametrize('slug', ['gpt-5.6-sol', 'GPT-6', 'gpt_6', '-gpt', 'gpt--6', '', 'a' * (SLUG_MAX_LENGTH + 1)])
def test_other_slugs_are_refused(slug: str):
    # 점은 결제 서버의 가격 코드(narration.<이름표>.i0.o0)에서 칸을 나눈다
    with pytest.raises(ValidationError):
        with_fields(LUNA, slug=slug)


def test_an_openai_model_needs_its_token_field():
    with pytest.raises(ValidationError, match='출력 상한의 칸'):
        with_fields(LUNA, token_limit_field=None)


def test_a_claude_model_takes_no_token_field():
    with pytest.raises(ValidationError, match='적지 않는다'):
        with_fields(OPUS, token_limit_field=TokenLimitField.MAX_TOKENS)


def test_a_claude_model_needs_its_reasoning_style():
    with pytest.raises(ValidationError, match='생각을 켜고 끄는 방식'):
        with_fields(OPUS, reasoning_style=None)


def test_an_openai_model_takes_no_reasoning_style():
    with pytest.raises(ValidationError, match='적지 않는다'):
        with_fields(LUNA, reasoning_style=ReasoningStyle.ADAPTIVE)


def test_a_claude_model_takes_only_the_claude_styles():
    with pytest.raises(ValidationError, match='받는 생각의 방식이 아니다'):
        with_fields(OPUS, reasoning_style=ReasoningStyle.LEVEL_MINIMAL)


def test_a_gemini_model_takes_only_the_gemini_styles():
    gemini = {'slug': 'gemini-4-argon', 'provider': Provider.GEMINI, 'api_model_id': 'gemini-4-argon'}

    assert with_fields(OPUS, **gemini, reasoning_style=ReasoningStyle.LEVEL_LOW).reasoning_style == 'level_low'
    # adaptive 는 Claude 의 방식이다
    with pytest.raises(ValidationError, match='받는 생각의 방식이 아니다'):
        with_fields(OPUS, **gemini, reasoning_style=ReasoningStyle.ADAPTIVE)


def test_a_zai_model_takes_a_switch_or_always_and_no_token_field():
    glm = {'slug': 'glm-4-7-flash', 'provider': Provider.ZAI, 'api_model_id': 'glm-4.7-flash'}

    assert with_fields(OPUS, **glm, reasoning_style=ReasoningStyle.THINKING_TYPE).reasoning_style == 'thinking_type'
    assert with_fields(OPUS, **glm, reasoning_style=ReasoningStyle.ALWAYS).reasoning_style == 'always'
    # thinking 칸으로 켜고 끄는 것은 Z.ai 의 방식이다. Claude 의 방식은 받지 않는다
    with pytest.raises(ValidationError, match='받는 생각의 방식이 아니다'):
        with_fields(OPUS, **glm, reasoning_style=ReasoningStyle.ADAPTIVE)
    # 출력 상한의 칸은 max_tokens 로 정해져 있다
    with pytest.raises(ValidationError, match='적지 않는다'):
        with_fields(OPUS, **glm, token_limit_field=TokenLimitField.MAX_TOKENS)


def test_a_deepinfra_model_takes_neither_a_style_nor_a_token_field():
    deepseek = {
        'slug': 'deepseek-v4-pro',
        'provider': Provider.DEEPINFRA,
        'api_model_id': 'deepseek-ai/DeepSeek-V4-Pro',
    }

    assert with_fields(OPUS, **deepseek, reasoning_style=None).provider == 'deepinfra'
    with pytest.raises(ValidationError, match='적지 않는다'):
        with_fields(OPUS, **deepseek, reasoning_style=ReasoningStyle.THINKING_TYPE)


@pytest.mark.parametrize('field', ['api_model_id', 'provider', 'grade', 'vendor'])
def test_odd_values_are_refused(field: str):
    odd = {'api_model_id': 'gpt 6', 'provider': 'bedrock', 'grade': 'gold', 'vendor': 'Open AI'}

    with pytest.raises(ValidationError):
        with_fields(LUNA, **{field: odd[field]})


def test_prices_are_not_negative():
    with pytest.raises(ValidationError):
        cost(input_price='-0.1')


def test_a_cached_input_dearer_than_the_input_is_refused():
    assert cost(input_price='1', cached_input_per_mtok=Decimal('1')).cached_input_per_mtok == Decimal('1')
    with pytest.raises(ValidationError, match='캐시 읽기'):
        cost(input_price='1', cached_input_per_mtok=Decimal('2'))


def test_prices_keep_six_decimal_places():
    assert cost(input_price='0.075').input_per_mtok == Decimal('0.075')
    with pytest.raises(ValidationError):
        cost(input_price='0.0000001')


def test_one_cost_a_day():
    assert len(with_fields(LUNA, costs=(cost(), cost('0.2', date(2026, 11, 1)))).costs) == 2
    with pytest.raises(ValidationError, match='같은 날'):
        with_fields(LUNA, costs=(cost(), cost('0.2')))


def test_slugs_and_api_models_are_unique_in_the_file():
    ModelCatalog(format=FORMAT, models=(LUNA, OPUS))
    with pytest.raises(ValidationError, match='이름표가 두 번'):
        ModelCatalog(format=FORMAT, models=(LUNA, with_fields(LUNA, api_model_id='other')))
    with pytest.raises(ValidationError, match='같은 API 모델'):
        ModelCatalog(format=FORMAT, models=(LUNA, with_fields(LUNA, slug='luna-again')))
    # 창구가 다르면 다른 모델이다
    ModelCatalog(format=FORMAT, models=(LUNA, with_fields(LUNA, slug='luna-local', provider=Provider.LOCAL)))


# --- 파일 ---


def test_the_file_is_read_with_decimals_and_dates():
    catalog = parse_catalog(LUNA_TOML)

    (luna,) = catalog.models
    (price,) = luna.costs
    # 0.1 이 float 로 틀어지지 않는다
    assert (price.input_per_mtok, price.cached_input_per_mtok, price.cache_write_per_mtok) == (
        Decimal('0.1'),
        Decimal('0.01'),
        None,
    )
    assert (luna.retires_on, price.effective_from, luna.supports_temperature) == (date(2027, 6, 1), TODAY, True)


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('format = [', 'TOML 이 아니다'),
        ('models = []', 'format = 1'),
        ('format = 2', '파일은 2'),
        (LUNA_TOML.replace('grade = "standard"', 'grade = "standard"\ncolor = "blue"'), 'models.0.color'),
        (LUNA_TOML.replace('input_per_mtok = 0.1', 'input_per_mtok = -1'), 'models.0.costs.0.input_per_mtok'),
        (LUNA_TOML + LUNA_TOML.replace('format = 1', ''), '이름표가 두 번'),
    ],
    ids=['not-toml', 'no-format', 'later-format', 'unknown-field', 'negative-price', 'twice'],
)
def test_a_wrong_file_says_where(text: str, expected: str):
    with pytest.raises(CatalogFileError) as caught:
        parse_catalog(text)

    assert expected in '\n'.join(caught.value.problems)
    assert str(caught.value) == '\n'.join(caught.value.problems)


def test_a_given_path_is_read(tmp_path: Path):
    path = tmp_path / 'catalog.toml'
    path.write_text(LUNA_TOML, encoding='utf-8')

    assert [model.slug for model in load_catalog(path).models] == ['gpt-6-luna']


def test_a_missing_path_is_a_file_error(tmp_path: Path):
    with pytest.raises(CatalogFileError, match='읽을 수 없다'):
        load_catalog(tmp_path / 'nothing.toml')


# --- 저장소의 파일 ---


@pytest.fixture(scope='module')
def repository_catalog() -> ModelCatalog:
    return load_catalog()


def test_the_repository_file_is_read(repository_catalog: ModelCatalog):
    assert len(repository_catalog.models) > 0


def test_every_model_has_a_cost(repository_catalog: ModelCatalog):
    # 원가를 모르면 켤 수 없다(서비스의 enable). 파일에 넣는 모델은 공식 가격표의 값을 함께 적는다
    assert [model.slug for model in repository_catalog.models if not model.costs] == []


def test_the_price_codes_fit_the_billing_limit(repository_catalog: ModelCatalog):
    # 결제 서버의 가격 코드 narration.<이름표>.i0.o0 는 64자까지다
    assert all(len(f'narration.{model.slug}.i0.o0') <= 64 for model in repository_catalog.models)


def test_no_check_day_is_in_the_future(repository_catalog: ModelCatalog):
    # 미리 알린 값 바꿈(행사가 끝, 인상)은 확인한 날보다 뒤에 시작해도 된다. 확인한 날은 오늘보다 뒤일 수 없다
    latest_check = max(cost.checked_on for model in repository_catalog.models for cost in model.costs)

    assert latest_check <= date.today()
