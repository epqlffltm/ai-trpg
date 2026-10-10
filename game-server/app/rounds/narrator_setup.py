# game-server/app/rounds/narrator_setup.py

"""
설정을 보고 어느 서술자를 쓸지 고른다. 앱을 만들 때 한 번 부른다(app/main.py).

서술자를 고르는 일을 앱을 만드는 함수에서 떼어 둔다. 고르는 규칙만 따로 테스트할 수 있다.
다른 provider(클라우드 API)를 더할 때도 여기만 고친다.
"""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.call_log import DbCallLog
from app.ai.openai_compat import OpenAICompatProvider
from app.core.config import Settings
from app.rounds.llm_narrator import LLMNarrator
from app.rounds.narrator import FakeNarrator, Narrator
from app.rounds.retrying_narrator import RetryingNarrator


def build_provider(settings: Settings, client: httpx.AsyncClient, model: str) -> OpenAICompatProvider:
    """설정의 주소로 그 모델을 부르는 provider 를 만든다. 만드는 것만으로는 모델을 부르지 않는다."""
    return OpenAICompatProvider(
        client=client,
        base_url=settings.llm_base_url,
        model=model,
        timeout=settings.llm_timeout_seconds,
        supports_reasoning=settings.llm_supports_reasoning,
    )


def build_narrator(
    settings: Settings, client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> Narrator:
    """
    설정이 llm 이면 언어 모델로 서술하는 서술자, 아니면 가짜 서술자.

    언어 모델이면 모델마다 서술자를 하나씩 만들어(첫 모델, 넘어갈 모델들 차례로) 다시 시도하는 서술자로 감싼다.
    모두 같은 기록장에 쓴다(ai_invocations). 가짜는 모델을 부르지 않으니 남길 것이 없다.
    """
    if settings.narrator != 'llm':
        return FakeNarrator()
    log = DbCallLog(session_factory)
    narrators = [LLMNarrator(build_provider(settings, client, model), log) for model in settings.llm_models()]
    return RetryingNarrator(narrators, attempt_timeout=settings.llm_timeout_seconds)
