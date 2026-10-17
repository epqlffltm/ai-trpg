# game-server/tests/test_model_routing.py

"""
모델의 이름으로 창구를 고르는 것(app/ai/routing.py)과, 그것으로 부를 때 고르는 서술자·장부 초안을 검증한다.

실제 모델을 부르지 않는다. httpx 의 가짜 전송이 서버 곁의 모델과 OpenAI 인 척 답한다.
모델 목록은 사전으로 흉내 낸다(FakeLookup). DB 에서 읽는 것(DbModelLookup)은 맨 아래에서 본다.
"오늘"은 테스트가 정한다.

넷을 본다.
  - 고르기: 목록에 없는 이름은 서버 곁의 모델, 목록의 모델은 목록의 창구·날짜판·받는 칸.
  - 못 고르기: 꺼짐, 은퇴, 키 없음, 코드 없는 창구. 다른 모델로 바꿔 부르지 않는다. warning 한 줄.
  - 부르기: 고른 대로 보낸다(주소, 키, 칸). 서술자와 장부 초안이 부를 때마다 고른다.
  - DB: 목록을 부를 때마다 읽는다. 끄면 다음 서술부터 바로 맞는다.
"""

import json
import logging
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.fake import FakeCallLog
from app.ai.openai_compat import WireOptions
from app.ai.provider import ProviderError
from app.ai.routing import (
    MODEL_UNAVAILABLE,
    PROVIDER_NOT_CONFIGURED,
    PROVIDER_UNSUPPORTED,
    Endpoint,
    ModelRouter,
)
from app.catalog import service
from app.catalog.lookup import CatalogModel, DbModelLookup
from app.catalog.models import Grade, Provider, TokenLimitField
from app.catalog.schemas import ModelCreate, ModelUpdate
from app.drafts.context import DraftContext
from app.drafts.routed_writer import RoutedDraftWriter
from app.drafts.validation import NOTHING
from app.drafts.writer import DraftRequest
from app.rounds.narrator import Move, NarrationRequest, StoryContext
from app.rounds.retrying_narrator import NarrationFailed, RetryingNarrator
from app.rounds.routed_narrator import RoutedNarrator
from tests.previews import RecordingPreview

TODAY = date(2026, 10, 17)
LOCAL_URL = 'http://127.0.0.1:11434/v1'
OPENAI_URL = 'https://api.openai.com/v1'
KEY = 'sk-test'
ROUTING_LOGGER = 'app.ai.routing'
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
OPUS = replace(LUNA, slug='claude-opus-5-5', provider=Provider.ANTHROPIC, token_limit_field=None)


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
    """그 모델들이 든 목록으로 고르는 것. 키를 빼면 OpenAI 의 창구가 없다."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(transport or Transport()))
    openai = Endpoint(OPENAI_URL, SecretStr(KEY), 'openai') if with_key else None
    return ModelRouter(
        lookup=lookup or FakeLookup({model.slug: model for model in models}),
        client=client,
        local=Endpoint(LOCAL_URL, None, 'openai_compat'),
        openai=openai,
        timeout=30,
        local_options=WireOptions(supports_reasoning=False),
        today=lambda: TODAY,
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


async def test_a_provider_without_code_is_unsupported():
    assert await refused(make_router(OPUS), 'claude-opus-5-5') == PROVIDER_UNSUPPORTED


async def test_a_refusal_leaves_a_warning(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger=ROUTING_LOGGER):
        await refused(make_router(replace(LUNA, enabled=False)), 'gpt-6-luna')

    (record,) = [record for record in caplog.records if record.name == ROUTING_LOGGER]
    assert (record.levelname, record.model, record.reason) == ('WARNING', 'gpt-6-luna', MODEL_UNAVAILABLE)


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


async def test_drafts_are_skipped_when_the_model_is_unavailable():
    lookup = FakeLookup({'gpt-6-luna': replace(LUNA, enabled=False)})
    log = FakeCallLog()
    writer = RoutedDraftWriter('gpt-6-luna', make_router(lookup=lookup), log)

    checked = await writer.draft(DraftRequest(scene=SCENE, context=DraftContext(characters={}, items={}, quests={})))

    # 초안은 덤이다. 고르지 못하면 없이 지나간다. 부르지 않았으니 기록도 없다
    assert checked is NOTHING
    assert (lookup.found, log.records) == (['gpt-6-luna'], [])


# --- DB ---

LUNA_ROW = ModelCreate(
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
    await service.add_model(session, LUNA_ROW)
    lookup = DbModelLookup(app.state.session_factory)

    found = await lookup.find('gpt-6-luna', TODAY)

    # 세션과 떨어진 값이다. 나중에 캐시에 담아 여럿이 읽어도 된다
    assert found == replace(LUNA, enabled=False)
    assert await lookup.find('gemma4:26b', TODAY) is None


@pytest.mark.usefixtures('clean_tables')
async def test_the_database_lookup_sees_a_change_at_once(app, session: AsyncSession):
    await service.add_model(session, LUNA_ROW)
    lookup = DbModelLookup(app.state.session_factory)
    before = await lookup.find('gpt-6-luna', TODAY)

    await service.update_model(session, 'gpt-6-luna', ModelUpdate(supports_temperature=True))

    assert (before.supports_temperature, (await lookup.find('gpt-6-luna', TODAY)).supports_temperature) == (False, True)
