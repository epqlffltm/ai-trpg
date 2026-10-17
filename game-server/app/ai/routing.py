# game-server/app/ai/routing.py

"""
모델의 이름으로 그 모델을 부를 provider 를 고른다. 서술과 장부 초안이 부를 때마다 쓴다.

이름은 설정(LLM_MODEL, LLM_PREMIUM_MODEL …)에 적은 것이다. 둘 중 하나다.
  - 모델 목록(app/catalog)의 이름표(gpt-6-luna): 목록에 적힌 창구, 날짜판(API 모델 이름), 받는 칸으로 부른다.
  - 목록에 없는 이름(gemma4:26b): 지금까지처럼 서버 곁의 모델(LLM_BASE_URL)로 그 이름을 부른다.
그래서 모델 목록을 비워 두면 예전과 똑같이 돈다.

목록의 모델을 부를 수 없으면 ProviderError 다. 다른 모델로 바꿔 부르지 않는다. 값이 다른 모델로 몰래 넘어가지 않는다.
  - model_unavailable: 꺼졌거나 은퇴했다. 관리 명령으로 켜야 한다(scripts/models.py).
  - provider_not_configured: 그 창구의 키가 없다(OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY).
  - provider_unsupported: 그 창구를 부르는 코드가 아직 없다. 지금은 모든 창구에 코드가 있다. 새 창구를 더할 때 쓴다.
이때는 부르지 않았으므로 호출의 기록(ai_invocations)이 없다. 대신 warning 한 줄을 남긴다.

평가(scripts/try_model.py)는 꺼진 모델도 부른다(allow_disabled). 켜기 전에 평가 장면을 돌려야 하기 때문이다.
은퇴한 모델은 평가에서도 부르지 않는다. 공급자가 내린 모델이다.

키는 설정에서 비밀값(SecretStr)으로 받아 provider 에 그대로 넘긴다. 여기서 꺼내 보지 않는다.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
from pydantic import SecretStr

from app.ai.anthropic import AnthropicProvider
from app.ai.costs import PriceTag
from app.ai.gemini import GeminiProvider
from app.ai.openai_compat import DEFAULT_TOKEN_FIELD, LOCAL_OPTIONS, OpenAICompatProvider, WireOptions
from app.ai.provider import LLMProvider, ProviderError
from app.catalog.lookup import CatalogModel, ModelLookup
from app.catalog.models import Provider, ReasoningStyle
from app.catalog.rules import is_offered, is_retired

logger = logging.getLogger(__name__)

# 목록의 모델을 부를 수 없는 이유들(위의 docstring)
MODEL_UNAVAILABLE = 'model_unavailable'
PROVIDER_NOT_CONFIGURED = 'provider_not_configured'
PROVIDER_UNSUPPORTED = 'provider_unsupported'
# 다른 모델로 넘어가도 소용없는 것이 아니라, 이 모델로 다시 불러도 소용없는 이유들이다
UNROUTABLE = frozenset({MODEL_UNAVAILABLE, PROVIDER_NOT_CONFIGURED, PROVIDER_UNSUPPORTED})

# 기록에 적는 창구의 이름. 서버 곁의 모델은 예전 이름 그대로다
LOCAL_KIND = 'openai_compat'
OPENAI_KIND = 'openai'
ANTHROPIC_KIND = 'anthropic'
GEMINI_KIND = 'gemini'


def today_utc() -> date:
    """오늘(UTC). 은퇴일과 견준다."""
    return datetime.now(UTC).date()


@dataclass(frozen=True)
class Route:
    """고른 것. 부를 provider 와, 모델 목록의 모델이면 그 이름표와 그날의 단가(price). 목록에 없으면 price 는 None."""

    provider: LLMProvider
    price: PriceTag | None


@dataclass(frozen=True)
class Endpoint:
    """창구 하나. 주소와 키(없으면 None)와 기록에 적는 이름."""

    base_url: str
    api_key: SecretStr | None
    kind: str


def options_of(model: CatalogModel) -> WireOptions:
    """목록의 모델이 받는 칸."""
    return WireOptions(
        supports_reasoning=model.supports_reasoning,
        supports_temperature=model.supports_temperature,
        token_field=model.token_limit_field or DEFAULT_TOKEN_FIELD,
    )


def check_callable(model: CatalogModel, today: date, allow_disabled: bool) -> None:
    """그날 부를 수 있는 모델이어야 한다. 은퇴했으면 언제나, 꺼졌으면 평가가 아닐 때 model_unavailable."""
    if is_retired(model, today):
        raise ProviderError(MODEL_UNAVAILABLE)
    if not allow_disabled and not is_offered(model, today):
        raise ProviderError(MODEL_UNAVAILABLE)


@dataclass(frozen=True)
class ModelRouter:
    """
    이름으로 provider 를 고른다. 앱에 하나 둔다(app/rounds/narrator_setup.py 의 build_router).

    lookup: 모델 목록에서 찾는 것(app/catalog/lookup.py). 지금은 부를 때마다 DB 에서 읽는다.
    local: 서버 곁의 모델의 창구(LLM_BASE_URL). openai, anthropic, gemini: 외부 API 의 창구. 키가 없으면 None 이다.
    local_options: 서버 곁의 모델이 받는 칸(LLM_SUPPORTS_REASONING). 목록에 없는 이름에 쓴다.
    today 는 테스트가 바꿔 꽂는다.
    """

    lookup: ModelLookup
    client: httpx.AsyncClient
    local: Endpoint
    openai: Endpoint | None
    timeout: float
    local_options: WireOptions = LOCAL_OPTIONS
    today: Callable[[], date] = today_utc
    anthropic: Endpoint | None = None
    gemini: Endpoint | None = None

    def endpoint_for(self, provider: Provider) -> Endpoint:
        """창구의 이름으로 창구를 고른다. 키가 없거나 코드가 없으면 ProviderError."""
        if provider == Provider.LOCAL:
            return self.local
        external = {Provider.OPENAI: self.openai, Provider.ANTHROPIC: self.anthropic, Provider.GEMINI: self.gemini}
        if provider not in external:
            raise ProviderError(PROVIDER_UNSUPPORTED)
        endpoint = external[provider]
        if endpoint is None:
            raise ProviderError(PROVIDER_NOT_CONFIGURED)
        return endpoint

    def build(self, endpoint: Endpoint, model: str, options: WireOptions) -> OpenAICompatProvider:
        """창구와 모델 이름과 받는 칸으로 provider 를 만든다. 만드는 것만으로는 부르지 않는다."""
        return OpenAICompatProvider(
            client=self.client,
            base_url=endpoint.base_url,
            model=model,
            timeout=self.timeout,
            options=options,
            api_key=endpoint.api_key,
            kind=endpoint.kind,
        )

    def build_claude(self, endpoint: Endpoint, model: CatalogModel) -> AnthropicProvider:
        """Claude 를 부르는 provider. 생각의 방식과 온도는 모델 목록의 값이다."""
        return AnthropicProvider(
            client=self.client,
            base_url=endpoint.base_url,
            model=model.api_model_id,
            api_key=endpoint.api_key,
            reasoning_style=model.reasoning_style or ReasoningStyle.ADAPTIVE,
            supports_temperature=model.supports_temperature,
            timeout=self.timeout,
            kind=endpoint.kind,
        )

    def build_gemini(self, endpoint: Endpoint, model: CatalogModel) -> GeminiProvider:
        """Gemini 를 부르는 provider. 생각의 방식과 온도는 모델 목록의 값이다."""
        return GeminiProvider(
            client=self.client,
            base_url=endpoint.base_url,
            model=model.api_model_id,
            api_key=endpoint.api_key,
            reasoning_style=model.reasoning_style or ReasoningStyle.LEVEL_LOW,
            supports_temperature=model.supports_temperature,
            timeout=self.timeout,
            kind=endpoint.kind,
        )

    def from_catalog(self, model: CatalogModel, allow_disabled: bool) -> LLMProvider:
        """목록의 모델을 부를 provider. 창구마다 부르는 코드가 다르다. 부를 수 없으면 ProviderError."""
        check_callable(model, self.today(), allow_disabled)
        endpoint = self.endpoint_for(model.provider)
        if model.provider == Provider.ANTHROPIC:
            return self.build_claude(endpoint, model)
        if model.provider == Provider.GEMINI:
            return self.build_gemini(endpoint, model)
        return self.build(endpoint, model.api_model_id, options_of(model))

    async def route(self, name: str, allow_disabled: bool = False) -> Route:
        """
        그 이름의 모델을 부를 provider 와 매길 단가. 목록에 없는 이름이면 서버 곁의 모델이고 단가가 없다.

        목록의 모델을 부를 수 없으면 warning 한 줄을 남기고 ProviderError 를 올린다.
        """
        model = await self.lookup.find(name, self.today())
        if model is None:
            return Route(self.build(self.local, name, self.local_options), price=None)
        try:
            provider = self.from_catalog(model, allow_disabled)
        except ProviderError as error:
            logger.warning('모델 목록의 모델을 부를 수 없습니다: %s', name, extra={'model': name, 'reason': str(error)})
            raise
        return Route(provider, PriceTag(model.slug, model.cost))

    async def provider_for(self, name: str, allow_disabled: bool = False) -> LLMProvider:
        """그 이름의 모델을 부를 provider. route 에서 단가를 뺀 것이다."""
        return (await self.route(name, allow_disabled)).provider
