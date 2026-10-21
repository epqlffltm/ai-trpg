# trpg-server/tests/test_deepinfra_provider.py

"""
DeepInfra 창구(#398)를 검증한다. DeepSeek 의 공개 가중치를 중국 본토가 아닌 곳(미국)에서 띄운 호스팅이다.

OpenAI 와 같은 모양이라 OpenAI 의 provider(ai_core/openai_compat.py)로 부른다. 주소와 키만 다르다.
실제 API 는 부르지 않는다. 가짜 전송(tests/test_model_routing.py 의 Transport)에 보낸 요청을 본다.

보는 것.
  - 목록의 deepinfra 모델은 DeepInfra 의 주소로, 키를 머리에 싣고, 날짜판의 이름으로 부른다.
  - 서술은 생각을 끈다. OpenAI 처럼 reasoning_effort 를 none 으로 보낸다. Z.ai 의 thinking 칸은 싣지 않는다.
  - 출력 상한의 칸은 max_tokens 로 정해져 있다. 모델 목록에 칸이나 생각의 방식을 적으면 받지 않는다.
  - 기록에는 deepinfra 창구라고 남는다. 키가 없으면 부르지 않는다(provider_not_configured).
  - 설정의 키와 주소가 창구로 간다. 키는 repr 에 나오지 않는다. 테스트는 .env 의 진짜 키를 쥐지 않는다.
  - DB 의 CHECK 도 새 창구를 받는다.
"""

import pytest
from ai_core.catalog_contract import CatalogModel, Provider, ReasoningStyle
from ai_core.fake import FakeCallLog
from ai_core.routing import DEEPINFRA_KIND, PROVIDER_NOT_CONFIGURED
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service
from app.catalog.models import Grade
from app.catalog.schemas import ModelCreate
from app.rounds.routed_narrator import RoutedNarrator
from tests.conftest import make_test_settings
from tests.test_model_catalog import OPUS
from tests.test_model_routing import DEEPINFRA_URL, KEY, SCENE, Transport, make_router, refused, request
from tests.test_narrator_setup import LLM, router_of

# 날짜판이 붙은 이름이다. 별칭은 호스팅이 말없이 다른 모델로 돌릴 수 있다
DEEPSEEK = CatalogModel(
    slug='deepseek-v4-pro',
    provider=Provider.DEEPINFRA,
    api_model_id='deepseek-ai/DeepSeek-V4-Pro-0813',
    supports_reasoning=True,
    supports_temperature=True,
    token_limit_field=None,
    enabled=True,
    retires_on=None,
)


async def test_a_deepinfra_model_is_called_like_openai_with_reasoning_off():
    transport = Transport()
    log = FakeCallLog()
    narrator = RoutedNarrator('deepseek-v4-pro', make_router(DEEPSEEK, transport=transport), log)

    assert await narrator.narrate(request()) == SCENE

    (sent,) = transport.requests
    assert str(sent.url) == f'{DEEPINFRA_URL}/chat/completions'
    assert sent.headers['Authorization'] == f'Bearer {KEY}'
    body = transport.body()
    assert body['model'] == 'deepseek-ai/DeepSeek-V4-Pro-0813'
    # 서술은 생각을 끈다. none 을 보내야 꺼진다. Z.ai 의 칸은 싣지 않는다
    assert body['reasoning_effort'] == 'none'
    assert 'thinking' not in body
    assert 'max_tokens' in body and 'max_completion_tokens' not in body
    assert 'temperature' in body
    (record,) = log.records
    assert record.provider == 'deepinfra'


async def test_a_deepinfra_model_without_a_key_is_not_configured():
    assert await refused(make_router(DEEPSEEK, with_key=False), 'deepseek-v4-pro') == PROVIDER_NOT_CONFIGURED


def test_a_deepinfra_model_takes_no_token_field_and_no_reasoning_style():
    deepseek = {
        **OPUS.model_dump(),
        'slug': 'deepseek-v4-pro',
        'provider': Provider.DEEPINFRA,
        'api_model_id': 'deepseek-ai/DeepSeek-V4-Pro-0813',
        'reasoning_style': None,
        'token_limit_field': None,
    }

    assert ModelCreate(**deepseek).provider == 'deepinfra'
    # 생각은 reasoning_effort 하나로 켜고 끈다. 생각의 방식은 적지 않는다
    with pytest.raises(ValidationError, match='적지 않는다'):
        ModelCreate(**{**deepseek, 'reasoning_style': ReasoningStyle.THINKING_TYPE})
    # 출력 상한의 칸은 max_tokens 로 정해져 있다
    with pytest.raises(ValidationError, match='적지 않는다'):
        ModelCreate(**{**deepseek, 'token_limit_field': 'max_tokens'})


def test_the_deepinfra_endpoint_carries_the_key_of_the_settings():
    router = router_of(make_test_settings(**LLM, deepinfra_api_key='di-test'))

    assert (router.deepinfra.base_url, router.deepinfra.kind) == (DEEPINFRA_URL, DEEPINFRA_KIND)
    assert router.deepinfra.api_key.get_secret_value() == 'di-test'
    assert 'di-test' not in repr(router)
    assert router_of(make_test_settings(**LLM)).deepinfra is None


@pytest.mark.usefixtures('clean_tables')
async def test_the_database_takes_a_deepinfra_model(session: AsyncSession):
    data = ModelCreate(
        slug='deepseek-v4-pro',
        provider=Provider.DEEPINFRA,
        api_model_id='deepseek-ai/DeepSeek-V4-Pro-0813',
        display_name='DeepSeek V4 Pro',
        vendor='deepseek',
        grade=Grade.STANDARD,
        supports_reasoning=True,
    )

    model = await service.add_model(session, data)

    # 새로 넣은 모델은 꺼져 있다. 원가를 적고 평가 장면을 통과한 뒤에 켠다
    assert (model.provider, model.reasoning_style, model.enabled) == ('deepinfra', None, False)
