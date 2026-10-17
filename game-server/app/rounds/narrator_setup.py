# game-server/app/rounds/narrator_setup.py

"""
설정을 보고 어느 서술자를 쓸지 고른다. 앱을 만들 때 한 번 부른다(app/main.py).

서술자를 고르는 일을 앱을 만드는 함수에서 떼어 둔다. 고르는 규칙만 따로 테스트할 수 있다.

서술 등급(app/rounds/tiers.py)마다 부를 모델들을 설정이 정한다(tier_models).
모델을 적은 등급만 방장에게 내준다(offered_tiers). 가짜 서술자는 모델을 부르지 않으므로 모든 등급을 내준다.

모델마다 어느 창구로 부를지는 서술할 때 고른다(app/ai/routing.py 의 ModelRouter, app/rounds/routed_narrator.py).
설정에 적은 이름이 모델 목록의 이름표면 목록대로, 아니면 서버 곁의 모델(LLM_BASE_URL)이다.
고르는 것(build_router)도 앱에 하나만 만든다. 장부 초안(app/drafts/setup.py)도 같은 것을 쓴다.
"""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.call_log import DbCallLog
from app.ai.calls import CallLog
from app.ai.openai_compat import WireOptions
from app.ai.routing import ANTHROPIC_KIND, GEMINI_KIND, LOCAL_KIND, OPENAI_KIND, Endpoint, ModelRouter
from app.catalog.lookup import DbModelLookup
from app.core.config import Settings
from app.rounds.fake_narrator import FakeNarrator
from app.rounds.narrator import Narrator
from app.rounds.retrying_narrator import RetryingNarrator
from app.rounds.routed_narrator import RoutedNarrator
from app.rounds.tiered_narrator import TieredNarrator
from app.rounds.tiers import NarrationTier


def local_endpoint(settings: Settings) -> Endpoint:
    """서버 곁의 모델의 창구. 키가 없다."""
    return Endpoint(base_url=settings.llm_base_url, api_key=None, kind=LOCAL_KIND)


def openai_endpoint(settings: Settings) -> Endpoint | None:
    """OpenAI 의 창구. 키를 적지 않았으면 None 이다."""
    if not settings.openai_api_key.get_secret_value():
        return None
    return Endpoint(base_url=settings.openai_base_url, api_key=settings.openai_api_key, kind=OPENAI_KIND)


def anthropic_endpoint(settings: Settings) -> Endpoint | None:
    """Anthropic(Claude)의 창구. 키를 적지 않았으면 None 이다."""
    if not settings.anthropic_api_key.get_secret_value():
        return None
    return Endpoint(base_url=settings.anthropic_base_url, api_key=settings.anthropic_api_key, kind=ANTHROPIC_KIND)


def gemini_endpoint(settings: Settings) -> Endpoint | None:
    """Google(Gemini)의 창구. 키를 적지 않았으면 None 이다."""
    if not settings.gemini_api_key.get_secret_value():
        return None
    return Endpoint(base_url=settings.gemini_base_url, api_key=settings.gemini_api_key, kind=GEMINI_KIND)


def build_router(
    settings: Settings, client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> ModelRouter:
    """모델의 이름으로 provider 를 고르는 것. 모델 목록은 부를 때마다 DB 에서 읽는다."""
    return ModelRouter(
        lookup=DbModelLookup(session_factory),
        client=client,
        local=local_endpoint(settings),
        openai=openai_endpoint(settings),
        anthropic=anthropic_endpoint(settings),
        gemini=gemini_endpoint(settings),
        timeout=settings.llm_timeout_seconds,
        local_options=WireOptions(supports_reasoning=settings.llm_supports_reasoning),
    )


def tier_models(settings: Settings) -> dict[NarrationTier, list[str]]:
    """등급마다 부를 모델들(부를 차례대로). 모델을 적지 않은 등급은 들지 않는다. standard 는 늘 있다(LLM_MODEL)."""
    models = {NarrationTier.STANDARD: settings.llm_models(), NarrationTier.PREMIUM: settings.llm_premium_models()}
    return {tier: names for tier, names in models.items() if names}


def offered_tiers(settings: Settings) -> frozenset[NarrationTier]:
    """방장이 고를 수 있는 등급들. 가짜 서술자면 모두, 언어 모델이면 모델을 적은 등급만."""
    if settings.narrator != 'llm':
        return frozenset(NarrationTier)
    return frozenset(tier_models(settings))


def build_chain(settings: Settings, router: ModelRouter, log: CallLog, models: list[str]) -> RetryingNarrator:
    """
    모델마다 서술자를 하나씩 만들어(첫 모델, 넘어갈 모델들 차례로) 다시 시도하는 서술자로 감싼다. 한 등급의 서술자다.
    """
    key = settings.digest_key()
    narrators = [RoutedNarrator(model, router, log, digest_key=key) for model in models]
    return RetryingNarrator(narrators, attempt_timeout=settings.llm_timeout_seconds)


def build_narrator(
    settings: Settings, router: ModelRouter, session_factory: async_sessionmaker[AsyncSession]
) -> Narrator:
    """
    설정이 llm 이면 언어 모델로 서술하는 서술자, 아니면 가짜 서술자.

    언어 모델이면 등급마다 다시 시도하는 서술자를 하나씩 만들고, 라운드의 등급으로 고르는 서술자로 감싼다.
    모두 같은 기록장에 쓴다(ai_invocations). 가짜는 모델을 부르지 않으니 남길 것이 없다. 등급도 읽지 않는다.
    """
    if settings.narrator != 'llm':
        return FakeNarrator()
    log = DbCallLog(session_factory)
    chains = {tier: build_chain(settings, router, log, models) for tier, models in tier_models(settings).items()}
    return TieredNarrator(chains)
