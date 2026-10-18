# game-server/app/rounds/narrator_setup.py

"""
설정을 보고 어느 서술자를 쓸지 고른다. 앱을 만들 때 한 번 부른다(app/main.py).

서술자를 고르는 일을 앱을 만드는 함수에서 떼어 둔다. 고르는 규칙만 따로 테스트할 수 있다.

라운드는 테이블의 서술 모델로 서술한다(app/rounds/picked_narrator.py). 모델 하나만 같은 모델로 다시 시도한다.
모델이 없는 옛 라운드는 설정의 기본 모델들(LLM_MODEL, LLM_FALLBACK_MODELS)로 서술한다.

모델마다 어느 창구로 부를지는 서술할 때 고른다(app/ai/routing.py 의 ModelRouter, app/rounds/routed_narrator.py).
설정에 적은 이름이 모델 목록의 이름표면 목록대로, 아니면 서버 곁의 모델(LLM_BASE_URL)이다.
고르는 것(build_router)도 앱에 하나만 만든다.
"""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.call_log import DbCallLog
from app.ai.calls import CallLog
from app.ai.openai_compat import WireOptions
from app.ai.retry_budget import RetryBudget
from app.ai.routing import ANTHROPIC_KIND, GEMINI_KIND, LOCAL_KIND, OPENAI_KIND, ZAI_KIND, Endpoint, ModelRouter
from app.catalog.lookup import DbModelLookup
from app.core.config import Settings
from app.rounds.fake_narrator import FakeNarrator
from app.rounds.narrator import Narrator
from app.rounds.picked_narrator import PickedNarrator
from app.rounds.retrying_narrator import RetryingNarrator
from app.rounds.routed_narrator import RoutedNarrator


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


def zai_endpoint(settings: Settings) -> Endpoint | None:
    """Z.ai(GLM)의 창구. OpenAI 와 같은 모양이다. 키를 적지 않았으면 None 이다."""
    if not settings.zai_api_key.get_secret_value():
        return None
    return Endpoint(base_url=settings.zai_base_url, api_key=settings.zai_api_key, kind=ZAI_KIND)


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
        zai=zai_endpoint(settings),
        timeout=settings.llm_timeout_seconds,
        local_options=WireOptions(supports_reasoning=settings.llm_supports_reasoning),
    )


def build_chain(
    settings: Settings, router: ModelRouter, log: CallLog, models: list[str], retry_budget: RetryBudget
) -> RetryingNarrator:
    """
    모델마다 서술자를 하나씩 만들어(첫 모델, 넘어갈 모델들 차례로) 다시 시도하는 서술자로 감싼다.

    재시도 예산(retry_budget)은 앱에 하나다. 모든 서술자가 함께 쓴다(app/ai/retry_budget.py).
    """
    key = settings.digest_key()
    narrators = [RoutedNarrator(model, router, log, digest_key=key) for model in models]
    return RetryingNarrator(narrators, attempt_timeout=settings.llm_timeout_seconds, retry_budget=retry_budget)


def build_narrator(
    settings: Settings, router: ModelRouter, session_factory: async_sessionmaker[AsyncSession]
) -> Narrator:
    """
    설정이 llm 이면 언어 모델로 서술하는 서술자, 아니면 가짜 서술자.

    언어 모델이면 라운드의 모델 하나만 다시 시도하는 서술자로 서술한다(PickedNarrator). 넘어갈 모델이 없다.
    모델이 없는 옛 라운드는 설정의 기본 모델들을 차례로 다시 시도하는 서술자로 서술한다.
    모두 같은 기록장에 쓴다(ai_invocations). 가짜는 모델을 부르지 않으니 남길 것이 없다. 모델도 읽지 않는다.
    """
    if settings.narrator != 'llm':
        return FakeNarrator()
    log = DbCallLog(session_factory)
    budget = RetryBudget()
    default = build_chain(settings, router, log, settings.llm_models(), budget)
    return PickedNarrator(chain_for=lambda model: build_chain(settings, router, log, [model], budget), default=default)
