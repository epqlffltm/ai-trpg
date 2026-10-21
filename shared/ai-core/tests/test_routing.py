# shared/ai-core/tests/test_routing.py

"""
모델의 이름으로 창구를 고르는 것(ai_core/routing.py)을 검증한다.

실제 모델을 부르지 않는다. httpx 의 가짜 전송이 서버 곁의 모델과 OpenAI 인 척 답한다.
모델 목록은 사전으로 흉내 낸다(FakeLookup). "오늘"은 테스트가 정한다.

둘을 본다.
  - 고르기: 목록에 없는 이름은 서버 곁의 모델, 목록의 모델은 목록의 창구·날짜판·받는 칸.
  - 못 고르기: 꺼짐, 은퇴, 키 없음, 코드 없는 창구. 다른 모델로 바꿔 부르지 않는다. warning 한 줄.

고른 대로 부르는 서술자와 DB 의 모델 목록은 게임 서버의 테스트(trpg-server/tests/test_model_routing.py)가 본다.
"""

import json
import logging
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

import httpx
import pytest
from pydantic import SecretStr

from ai_core.anthropic import AnthropicProvider
from ai_core.catalog_contract import CatalogModel, Provider, ReasoningStyle, TokenLimitField
from ai_core.gemini import GeminiProvider
from ai_core.openai_compat import WireOptions
from ai_core.provider import ProviderError
from ai_core.routing import (
    MODEL_UNAVAILABLE,
    PROVIDER_NOT_CONFIGURED,
    Endpoint,
    ModelRouter,
)

TODAY = date(2026, 10, 17)
LOCAL_URL = 'http://127.0.0.1:11434/v1'
OPENAI_URL = 'https://api.openai.com/v1'
KEY = 'sk-test'
ROUTING_LOGGER = 'ai_core.routing'
SCENE = '엔진 소리가 골목을 메운다.'

LUNA = CatalogModel(
    slug='gpt-6-luna',
    provider=Provider.OPENAI,
    api_model_id='gpt-6-luna-2026-09-22',
    supports_reasoning=True,
    supports_temperature=False,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
    enabled=True,
    retires_on=None,
)
GEMMA = CatalogModel(
    slug='gemma-4',
    provider=Provider.LOCAL,
    api_model_id='gemma4:26b',
    supports_reasoning=False,
    supports_temperature=True,
    token_limit_field=TokenLimitField.MAX_TOKENS,
    enabled=True,
    retires_on=None,
)
OPUS = replace(
    LUNA,
    slug='claude-opus-5-5',
    provider=Provider.ANTHROPIC,
    api_model_id='claude-opus-5-5-20260901',
    token_limit_field=None,
    reasoning_style=ReasoningStyle.ALWAYS,
)
GEMINI = replace(
    LUNA,
    slug='gemini-4-argon',
    provider=Provider.GEMINI,
    api_model_id='gemini-4-argon',
    token_limit_field=None,
    reasoning_style=ReasoningStyle.LEVEL_LOW,
)
GLM = CatalogModel(
    slug='glm-4-7-flash',
    provider=Provider.ZAI,
    api_model_id='glm-4.7-flash',
    supports_reasoning=False,
    supports_temperature=True,
    token_limit_field=None,
    enabled=True,
    retires_on=None,
    reasoning_style=ReasoningStyle.THINKING_TYPE,
)
GLM_ALWAYS = replace(GLM, slug='glm-5-3', api_model_id='glm-5.3', reasoning_style=ReasoningStyle.ALWAYS)
GEMINI_URL = 'https://generativelanguage.googleapis.com'
ANTHROPIC_URL = 'https://api.anthropic.com'
ZAI_URL = 'https://api.z.ai/api/paas/v4'
DEEPINFRA_URL = 'https://api.deepinfra.com/v1/openai'


@dataclass
class FakeLookup:
    """사전으로 흉내 낸 모델 목록. 찾은 이름표가 쌓인다."""

    models: dict[str, CatalogModel] = field(default_factory=dict)
    found: list[str] = field(default_factory=list)

    async def find(self, slug: str, day: date) -> CatalogModel | None:
        assert day == TODAY
        self.found.append(slug)
        return self.models.get(slug)


def stream() -> str:
    """글 하나와 멈춘 이유, 토큰 수가 오는 답(SSE)."""
    pieces = [
        {'model': 'answer', 'choices': [{'index': 0, 'delta': {'content': SCENE}, 'finish_reason': None}]},
        {'model': 'answer', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]},
        {'model': 'answer', 'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 5}},
    ]
    return ''.join(f'data: {json.dumps(piece)}\n\n' for piece in pieces) + 'data: [DONE]\n\n'


@dataclass
class Transport:
    """받은 요청을 적어 두고 늘 같은 답을 흘려 보내는 가짜 전송."""

    requests: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, text=stream(), headers={'content-type': 'text/event-stream'})

    def body(self) -> dict:
        (request,) = self.requests
        return json.loads(request.content)


def make_router(
    *models: CatalogModel, transport: Transport | None = None, with_key: bool = True, lookup: FakeLookup | None = None
) -> ModelRouter:
    """그 모델들이 든 목록으로 고르는 것. 키를 빼면 OpenAI 와 Anthropic 의 창구가 없다."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(transport or Transport()))
    openai = Endpoint(OPENAI_URL, SecretStr(KEY), 'openai') if with_key else None
    anthropic = Endpoint(ANTHROPIC_URL, SecretStr(KEY), 'anthropic') if with_key else None
    gemini = Endpoint(GEMINI_URL, SecretStr(KEY), 'gemini') if with_key else None
    zai = Endpoint(ZAI_URL, SecretStr(KEY), 'zai') if with_key else None
    deepinfra = Endpoint(DEEPINFRA_URL, SecretStr(KEY), 'deepinfra') if with_key else None
    return ModelRouter(
        lookup=lookup or FakeLookup({model.slug: model for model in models}),
        client=client,
        local=Endpoint(LOCAL_URL, None, 'openai_compat'),
        openai=openai,
        timeout=30,
        local_options=WireOptions(supports_reasoning=False),
        today=lambda: TODAY,
        anthropic=anthropic,
        gemini=gemini,
        zai=zai,
        deepinfra=deepinfra,
    )


async def refused(router: ModelRouter, name: str, **options) -> str:
    """고르지 못한 이유."""
    with pytest.raises(ProviderError) as caught:
        await router.provider_for(name, **options)
    return str(caught.value)


# --- 고르기 ---


async def test_a_name_not_in_the_catalog_is_a_local_model():
    provider = await make_router(LUNA).provider_for('gemma4:31b-it-qat')

    # 예전과 같다. 설정의 주소로 그 이름을, 키 없이, 설정의 받는 칸으로 부른다
    assert (provider.base_url, provider.model, provider.api_key, provider.kind) == (
        LOCAL_URL,
        'gemma4:31b-it-qat',
        None,
        'openai_compat',
    )
    assert provider.options == WireOptions(supports_reasoning=False)
    assert provider.timeout == 30


async def test_a_catalog_model_is_called_through_its_provider_and_snapshot():
    provider = await make_router(LUNA).provider_for('gpt-6-luna')

    assert (provider.base_url, provider.model, provider.kind) == (OPENAI_URL, 'gpt-6-luna-2026-09-22', 'openai')
    assert provider.api_key.get_secret_value() == KEY
    assert provider.options == WireOptions(
        supports_reasoning=True, supports_temperature=False, token_field='max_completion_tokens'
    )


async def test_a_local_catalog_model_uses_the_local_endpoint_with_its_snapshot():
    provider = await make_router(GEMMA).provider_for('gemma-4')

    assert (provider.base_url, provider.model, provider.api_key) == (LOCAL_URL, 'gemma4:26b', None)
    assert provider.options == WireOptions(supports_reasoning=False, token_field='max_tokens')


async def test_a_model_that_retires_later_can_be_called():
    router = make_router(replace(LUNA, retires_on=TODAY + timedelta(days=1)))

    assert (await router.provider_for('gpt-6-luna')).model == 'gpt-6-luna-2026-09-22'


# --- 못 고르기 ---


async def test_a_disabled_model_is_unavailable():
    assert await refused(make_router(replace(LUNA, enabled=False)), 'gpt-6-luna') == MODEL_UNAVAILABLE


async def test_an_evaluation_may_call_a_disabled_model():
    # 켜기 전에 평가 장면을 돌려야 한다
    provider = await make_router(replace(LUNA, enabled=False)).provider_for('gpt-6-luna', allow_disabled=True)

    assert provider.model == 'gpt-6-luna-2026-09-22'


async def test_a_retired_model_is_unavailable_even_for_an_evaluation():
    router = make_router(replace(LUNA, retires_on=TODAY))

    assert await refused(router, 'gpt-6-luna') == MODEL_UNAVAILABLE
    assert await refused(router, 'gpt-6-luna', allow_disabled=True) == MODEL_UNAVAILABLE


async def test_an_openai_model_without_a_key_is_not_configured():
    assert await refused(make_router(LUNA, with_key=False), 'gpt-6-luna') == PROVIDER_NOT_CONFIGURED


async def test_a_local_model_needs_no_key():
    assert (await make_router(GEMMA, with_key=False).provider_for('gemma-4')).model == 'gemma4:26b'


async def test_a_gemini_model_is_called_through_the_gemini_endpoint():
    provider = await make_router(GEMINI).provider_for('gemini-4-argon')

    assert isinstance(provider, GeminiProvider)
    assert (provider.base_url, provider.model, provider.kind) == (GEMINI_URL, 'gemini-4-argon', 'gemini')
    assert provider.api_key.get_secret_value() == KEY
    assert (provider.reasoning_style, provider.supports_temperature) == (ReasoningStyle.LEVEL_LOW, False)


async def test_a_gemini_model_without_a_key_is_not_configured():
    assert await refused(make_router(GEMINI, with_key=False), 'gemini-4-argon') == PROVIDER_NOT_CONFIGURED


async def test_a_claude_model_is_called_through_the_anthropic_endpoint():
    provider = await make_router(OPUS).provider_for('claude-opus-5-5')

    assert isinstance(provider, AnthropicProvider)
    assert (provider.base_url, provider.model, provider.kind) == (
        ANTHROPIC_URL,
        'claude-opus-5-5-20260901',
        'anthropic',
    )
    assert provider.api_key.get_secret_value() == KEY
    # 생각의 방식과 온도는 모델 목록의 값이다
    assert (provider.reasoning_style, provider.supports_temperature, provider.timeout) == (
        ReasoningStyle.ALWAYS,
        False,
        30,
    )


async def test_a_claude_model_without_a_key_is_not_configured():
    assert await refused(make_router(OPUS, with_key=False), 'claude-opus-5-5') == PROVIDER_NOT_CONFIGURED


async def test_a_refusal_leaves_a_warning(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger=ROUTING_LOGGER):
        await refused(make_router(replace(LUNA, enabled=False)), 'gpt-6-luna')

    (record,) = [record for record in caplog.records if record.name == ROUTING_LOGGER]
    assert (record.levelname, record.model, record.reason) == ('WARNING', 'gpt-6-luna', MODEL_UNAVAILABLE)
