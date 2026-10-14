# game-server/app/drafts/setup.py

"""
설정을 보고 장부 초안을 쓸 것을 고른다. 앱을 만들 때 한 번 부른다(app/main.py).

서술자가 언어 모델이면 standard 등급의 첫 모델로 쓴다. 장면을 쓴 모델과 같은 것이다. 같은 기록장에 남긴다.
다시 시도하거나 다른 모델로 넘어가지 않는다. 초안은 덤이라 한 번 실패하면 그 라운드는 건너뛴다.
가짜 서술자면 아무것도 쓰지 않는다(NO_DRAFTS). 가짜가 쓴 장면에는 고를 사실이 없다.
"""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.call_log import DbCallLog
from app.core.config import Settings
from app.drafts.drafting import NO_DRAFTS, Drafter
from app.drafts.writer import DraftWriter
from app.rounds.narrator_setup import build_provider


def build_drafter(
    settings: Settings, client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> Drafter:
    """설정이 llm 이면 standard 등급의 첫 모델로 쓰는 것, 아니면 아무것도 쓰지 않는 것."""
    if settings.narrator != 'llm':
        return NO_DRAFTS
    provider = build_provider(settings, client, settings.llm_models()[0])
    return DraftWriter(provider, DbCallLog(session_factory), digest_key=settings.digest_key())
