# chat-server/app/turns/providers.py

"""
설정을 보고 모델을 부를 것(ai_core 의 ModelRouter)을 만든다. 앱을 만들 때 한 번 부른다(app/main.py).

게임 서버의 것(trpg-server/app/rounds/narrator_setup.py)에서 창구를 만드는 부분만 옮겼다.
대화의 모델은 언제나 모델 목록의 이름표다(conversations.model_slug 의 외래 키).
목록대로 창구, 날짜판, 받는 칸으로 부른다.
키가 없는 창구의 모델은 부르지 않는다(provider_not_configured). 다른 모델로 바꿔 부르지 않는다.
"""

from typing import Protocol

import httpx
from ai_core.routing import (
    ANTHROPIC_KIND,
    DEEPINFRA_KIND,
    GEMINI_KIND,
    LOCAL_KIND,
    OPENAI_KIND,
    ZAI_KIND,
    Endpoint,
    ModelRouter,
    Route,
)
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.catalog.lookup import DbModelLookup
from app.core.config import Settings


class Router(Protocol):
    """이름표로 provider 를 고르는 것의 모양. 테스트는 가짜(tests/models.py)를 꽂는다."""

    async def route(self, name: str, allow_disabled: bool = False) -> Route:
        """그 이름표의 모델을 부를 provider 와 매길 단가. 부를 수 없으면 ai_core 의 ProviderError."""
        ...


def endpoint(base_url: str, api_key: SecretStr, kind: str) -> Endpoint | None:
    """키가 있는 창구. 키를 적지 않았으면 None 이다."""
    if not api_key.get_secret_value():
        return None
    return Endpoint(base_url=base_url, api_key=api_key, kind=kind)


def build_router(
    settings: Settings, client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> ModelRouter:
    """모델의 이름표로 provider 를 고르는 것. 모델 목록은 부를 때마다 DB 에서 읽는다(app/catalog/lookup.py)."""
    return ModelRouter(
        lookup=DbModelLookup(session_factory),
        client=client,
        local=Endpoint(base_url=settings.llm_base_url, api_key=None, kind=LOCAL_KIND),
        openai=endpoint(settings.openai_base_url, settings.openai_api_key, OPENAI_KIND),
        anthropic=endpoint(settings.anthropic_base_url, settings.anthropic_api_key, ANTHROPIC_KIND),
        gemini=endpoint(settings.gemini_base_url, settings.gemini_api_key, GEMINI_KIND),
        zai=endpoint(settings.zai_base_url, settings.zai_api_key, ZAI_KIND),
        deepinfra=endpoint(settings.deepinfra_base_url, settings.deepinfra_api_key, DEEPINFRA_KIND),
        timeout=settings.llm_timeout_seconds,
    )
