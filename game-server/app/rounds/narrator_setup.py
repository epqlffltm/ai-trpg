# game-server/app/rounds/narrator_setup.py

"""
설정을 보고 어느 서술자를 쓸지 고른다. 앱을 만들 때 한 번 부른다(app/main.py).

서술자를 고르는 일을 앱을 만드는 함수에서 떼어 둔다. 고르는 규칙만 따로 테스트할 수 있다.
다른 provider(클라우드 API)를 더할 때도 여기만 고친다.

서술 등급(app/rounds/tiers.py)마다 부를 모델들을 설정이 정한다(tier_models).
모델을 적은 등급만 방장에게 내준다(offered_tiers). 가짜 서술자는 모델을 부르지 않으므로 모든 등급을 내준다.
"""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.call_log import DbCallLog
from app.ai.calls import CallLog
from app.ai.openai_compat import OpenAICompatProvider
from app.core.config import Settings
from app.rounds.llm_narrator import LLMNarrator
from app.rounds.narrator import FakeNarrator, Narrator
from app.rounds.retrying_narrator import RetryingNarrator
from app.rounds.tiered_narrator import TieredNarrator
from app.rounds.tiers import NarrationTier


def build_provider(settings: Settings, client: httpx.AsyncClient, model: str) -> OpenAICompatProvider:
    """설정의 주소로 그 모델을 부르는 provider 를 만든다. 만드는 것만으로는 모델을 부르지 않는다."""
    return OpenAICompatProvider(
        client=client,
        base_url=settings.llm_base_url,
        model=model,
        timeout=settings.llm_timeout_seconds,
        supports_reasoning=settings.llm_supports_reasoning,
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


def build_chain(settings: Settings, client: httpx.AsyncClient, log: CallLog, models: list[str]) -> RetryingNarrator:
    """
    모델마다 서술자를 하나씩 만들어(첫 모델, 넘어갈 모델들 차례로) 다시 시도하는 서술자로 감싼다. 한 등급의 서술자다.
    """
    key = settings.digest_key()
    narrators = [LLMNarrator(build_provider(settings, client, model), log, digest_key=key) for model in models]
    return RetryingNarrator(narrators, attempt_timeout=settings.llm_timeout_seconds)


def build_narrator(
    settings: Settings, client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> Narrator:
    """
    설정이 llm 이면 언어 모델로 서술하는 서술자, 아니면 가짜 서술자.

    언어 모델이면 등급마다 다시 시도하는 서술자를 하나씩 만들고, 라운드의 등급으로 고르는 서술자로 감싼다.
    모두 같은 기록장에 쓴다(ai_invocations). 가짜는 모델을 부르지 않으니 남길 것이 없다. 등급도 읽지 않는다.
    """
    if settings.narrator != 'llm':
        return FakeNarrator()
    log = DbCallLog(session_factory)
    chains = {tier: build_chain(settings, client, log, models) for tier, models in tier_models(settings).items()}
    return TieredNarrator(chains)
