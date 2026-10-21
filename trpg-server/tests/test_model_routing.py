# trpg-server/tests/test_model_routing.py

"""
모델의 이름으로 창구를 고르는 것(ai_core/routing.py)으로 부를 때 고르는 서술자를 검증한다.

실제 모델을 부르지 않는다. httpx 의 가짜 전송이 서버 곁의 모델과 OpenAI 인 척 답한다.
모델 목록은 사전으로 흉내 낸다(FakeLookup). DB 에서 읽는 것(DbModelLookup)은 맨 아래에서 본다.
"오늘"은 테스트가 정한다. 고르기와 못 고르기는 공용 코드의 테스트(shared/ai-core/tests/test_routing.py)가 본다.
다른 테스트(test_deepinfra_provider.py)가 이 파일의 도구(make_router, refused 등)를 가져다 쓴다.

둘을 본다.
  - 부르기: 고른 대로 보낸다(주소, 키, 칸). 서술자가 부를 때마다 고른다.
  - DB: 목록을 부를 때마다 읽는다. 끄면 다음 서술부터 바로 맞는다.
"""

import json
from dataclasses import dataclass, field, replace
from datetime import date

import httpx
import pytest
from ai_core.catalog_contract import CatalogModel, Provider, ReasoningStyle, TokenLimitField
from ai_core.catalog_file import ModelEntry
from ai_core.fake import FakeCallLog
from ai_core.openai_compat import WireOptions
from ai_core.provider import ProviderError
from ai_core.routing import (
    MODEL_UNAVAILABLE,
    PROVIDER_NOT_CONFIGURED,
    Endpoint,
    ModelRouter,
)
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.lookup import DbModelLookup
from app.catalog.models import Grade
from app.rounds.narrator import Move, NarrationRequest, StoryContext
from app.rounds.retrying_narrator import NarrationFailed, RetryingNarrator
from app.rounds.routed_narrator import RoutedNarrator
from tests.catalog_rows import put_models
from tests.previews import RecordingPreview

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


# --- 부르기 ---


def request() -> NarrationRequest:
    """이야기의 바탕이 있는 서술 요청 하나."""
    story = StoryContext(title='추격전', rating='all', guide='추격은 언제나 바이크로 한다.')
    return NarrationRequest(round_number=1, scene='사이렌이 울린다.', moves=[Move('엘프', '달린다.')], story=story)


async def test_an_openai_call_carries_the_key_and_the_fields_the_model_takes():
    transport = Transport()
    log = FakeCallLog()
    narrator = RoutedNarrator('gpt-6-luna', make_router(LUNA, transport=transport), log)

    assert await narrator.narrate(request()) == SCENE

    (sent,) = transport.requests
    assert str(sent.url) == f'{OPENAI_URL}/chat/completions'
    assert sent.headers['Authorization'] == f'Bearer {KEY}'
    body = transport.body()
    assert body['model'] == 'gpt-6-luna-2026-09-22'
    # 생각하는 모델의 칸에 상한을 싣고, 받지 않는 온도는 싣지 않는다
    assert 'max_completion_tokens' in body
    assert 'max_tokens' not in body
    assert 'temperature' not in body
    # 기록에는 어느 창구였는지 적는다
    (record,) = log.records
    assert record.provider == 'openai'


async def test_a_zai_model_is_called_like_openai_with_its_thinking_switch():
    transport = Transport()
    log = FakeCallLog()
    narrator = RoutedNarrator('glm-4-7-flash', make_router(GLM, transport=transport), log)

    assert await narrator.narrate(request()) == SCENE

    (sent,) = transport.requests
    assert str(sent.url) == f'{ZAI_URL}/chat/completions'
    assert sent.headers['Authorization'] == f'Bearer {KEY}'
    body = transport.body()
    assert body['model'] == 'glm-4.7-flash'
    # 서술은 생각을 끈다. Z.ai 는 reasoning_effort 가 아니라 thinking 칸으로 끈다. 출력 상한은 max_tokens 다
    assert body['thinking'] == {'type': 'disabled'}
    assert 'reasoning_effort' not in body
    assert 'max_tokens' in body
    (record,) = log.records
    assert record.provider == 'zai'


async def test_a_zai_model_that_always_thinks_gets_the_thinking_share():
    always = await make_router(GLM_ALWAYS).provider_for('glm-5-3')
    switch = await make_router(GLM).provider_for('glm-4-7-flash')

    # 끌 수 없는 모델에는 끄라는 칸을 보내지 않고, 생각의 몫을 출력 상한에 더한다
    assert always.options == WireOptions(supports_reasoning=False, always_thinks=True)
    assert switch.options == WireOptions(supports_reasoning=False, thinking_switch=True)


async def test_a_zai_model_without_a_key_is_not_configured():
    assert await refused(make_router(GLM, with_key=False), 'glm-4-7-flash') == PROVIDER_NOT_CONFIGURED


async def test_a_local_call_sends_no_key():
    transport = Transport()

    await RoutedNarrator('gemma4:26b', make_router(transport=transport), FakeCallLog()).narrate(request())

    (sent,) = transport.requests
    assert str(sent.url) == f'{LOCAL_URL}/chat/completions'
    assert 'Authorization' not in sent.headers
    assert transport.body()['model'] == 'gemma4:26b'


async def test_the_narrator_chooses_at_every_narration():
    lookup = FakeLookup({'gpt-6-luna': LUNA})
    narrator = RoutedNarrator('gpt-6-luna', make_router(lookup=lookup), FakeCallLog())

    await narrator.narrate(request())
    # 관리 명령으로 끄면 서버를 다시 띄우지 않아도 다음 서술부터 맞는다
    lookup.models['gpt-6-luna'] = replace(LUNA, enabled=False)

    with pytest.raises(ProviderError, match=MODEL_UNAVAILABLE):
        await narrator.narrate(request())
    assert lookup.found == ['gpt-6-luna', 'gpt-6-luna']


async def test_an_unavailable_model_is_not_called_recorded_or_previewed():
    transport = Transport()
    log = FakeCallLog()
    preview = RecordingPreview()
    narrator = RoutedNarrator('gpt-6-luna', make_router(LUNA, transport=transport, with_key=False), log)

    with pytest.raises(ProviderError, match=PROVIDER_NOT_CONFIGURED):
        await narrator.narrate(request(), preview)

    assert (transport.requests, log.records, preview.attempts) == ([], [], [])


async def test_an_unavailable_model_is_not_tried_again():
    lookup = FakeLookup({'gpt-6-luna': replace(LUNA, enabled=False)})
    narrator = RoutedNarrator('gpt-6-luna', make_router(lookup=lookup), FakeCallLog())

    async def no_sleep(seconds: float) -> None:
        return None

    retrying = RetryingNarrator([narrator], attempt_timeout=30, sleep=no_sleep)

    with pytest.raises(NarrationFailed) as caught:
        await retrying.narrate(request())

    # 다시 불러도 꺼진 모델이다. 한 번만 찾고 그만둔다
    assert caught.value.reason == MODEL_UNAVAILABLE
    assert lookup.found == ['gpt-6-luna']


# --- DB ---

LUNA_ROW = ModelEntry(
    slug='gpt-6-luna',
    provider=Provider.OPENAI,
    api_model_id='gpt-6-luna-2026-09-22',
    display_name='GPT-6 Luna',
    vendor='openai',
    grade=Grade.STANDARD,
    supports_reasoning=True,
    supports_temperature=False,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
)


@pytest.mark.usefixtures('clean_tables')
async def test_the_database_lookup_finds_a_plain_value(app, session: AsyncSession):
    await put_models(session, LUNA_ROW)
    lookup = DbModelLookup(app.state.session_factory)

    found = await lookup.find('gpt-6-luna', TODAY)

    # 세션과 떨어진 값이다. 나중에 캐시에 담아 여럿이 읽어도 된다
    assert found == replace(LUNA, enabled=False)
    assert await lookup.find('gemma4:26b', TODAY) is None


@pytest.mark.usefixtures('clean_tables')
async def test_the_database_lookup_sees_a_change_at_once(app, session: AsyncSession):
    await put_models(session, LUNA_ROW)
    lookup = DbModelLookup(app.state.session_factory)
    before = await lookup.find('gpt-6-luna', TODAY)

    await put_models(session, LUNA_ROW.model_copy(update={'supports_temperature': True}))

    assert (before.supports_temperature, (await lookup.find('gpt-6-luna', TODAY)).supports_temperature) == (False, True)
