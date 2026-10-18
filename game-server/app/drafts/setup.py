# game-server/app/drafts/setup.py

"""
설정을 보고 장부 초안을 쓸 것을 고른다. 앱을 만들 때 한 번 부른다(app/main.py).

서술자가 언어 모델이면 DRAFT_MODEL 로 쓴다. 비워 두면 standard 등급의 첫 모델(LLM_MODEL)이다. 같은 기록장에 남긴다.
장부 초안은 청구하지 않는 호출이다. 방장이 고른 서술 모델로 부르지 않는다. 비싼 모델을 고른 테이블의 초안 원가가
그대로 우리 몫이 된다. 고르는 일이라 싼 모델로 충분하고, 틀린 답은 서버의 검증(app/drafts/validation.py)이 거른다.
어느 창구로 부를지는 서술자와 같은 것(app/ai/routing.py 의 ModelRouter)이 부를 때마다 고른다.
다시 시도하거나 다른 모델로 넘어가지 않는다. 초안은 덤이라 한 번 실패하면 그 라운드는 건너뛴다.
가짜 서술자면 아무것도 쓰지 않는다(NO_DRAFTS). 가짜가 쓴 장면에는 고를 사실이 없다.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.call_log import DbCallLog
from app.ai.routing import ModelRouter
from app.core.config import Settings
from app.drafts.drafting import NO_DRAFTS, Drafter
from app.drafts.routed_writer import RoutedDraftWriter


def build_drafter(
    settings: Settings, router: ModelRouter, session_factory: async_sessionmaker[AsyncSession]
) -> Drafter:
    """설정이 llm 이면 장부 초안의 모델(draft_model_name)로 쓰는 것, 아니면 아무것도 쓰지 않는 것."""
    if settings.narrator != 'llm':
        return NO_DRAFTS
    return RoutedDraftWriter(
        settings.draft_model_name(), router, DbCallLog(session_factory), digest_key=settings.digest_key()
    )
