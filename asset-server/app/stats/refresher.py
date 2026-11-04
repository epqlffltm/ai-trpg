# asset-server/app/stats/refresher.py

"""
몇 분마다 chat 과 story 서버에서 작품마다의 시작 수를 받아 와 바꿔 넣는 바퀴(#985).

  - 뜨자마자 한 번, 그 뒤 STATS_REFRESH_SECONDS 마다 받는다. 수는 그만큼 늦게 반영된다
  - 받을 곳은 설정에 주소가 있는 것만이다. 하나도 없으면 아무것도 하지 않는다
  - 한 곳을 받지 못하면 그 종류는 쌓아 둔 수를 그대로 두고 warning 을 남긴다(주소는 적지 않는다). 다른 곳은 받는다
  - 통째로 바꾸므로 서버가 여럿이어도, 다시 받아도 같은 결과다(멱등)
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from server_core import loops
from server_core.loops import Running
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.stats.client import StartsSource, StatsUnavailableError
from app.stats.models import WorkKind
from app.stats.repository import replace_starts

logger = logging.getLogger(__name__)

REFRESH_OPERATION = 'stats.refresh'


def utc_now() -> datetime:
    """지금 시각(UTC)."""
    return datetime.now(UTC)


class StartsRefresher:
    """받을 곳들과 받은 수를 넣을 DB. run 이 바퀴를 돈다."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        client: httpx.AsyncClient,
        sources: list[StartsSource],
        interval: float,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.session_factory = session_factory
        self.client = client
        self.sources = sources
        self.interval = interval
        self.clock = clock

    async def refresh_one(self, source: StartsSource) -> bool:
        """한 곳을 받아 바꿔 넣는다. 받았으면 True 다. 받지 못하면 쌓아 둔 수를 그대로 둔다."""
        try:
            received = await source.fetch(self.client)
        except StatsUnavailableError as error:
            logger.warning(
                '작품의 시작 수를 받지 못했다. 쌓아 둔 수를 그대로 쓴다',
                extra={
                    'operation': REFRESH_OPERATION,
                    'result': 'server_error',
                    'kind': source.kind,
                    'reason': error.reason,
                },
            )
            return False
        async with self.session_factory() as session:
            await replace_starts(session, source.kind, received, self.clock())
            await session.commit()
        return True

    async def refresh(self) -> None:
        """모든 곳을 한 번씩 받는다."""
        for source in self.sources:
            await self.refresh_one(source)

    async def run(self, stop: asyncio.Event) -> None:
        """stop 이 켜질 때까지 바로 한 번, 그 뒤 interval 마다 받는다. 받을 곳이 없으면 바로 끝난다."""
        if not self.sources:
            return
        while not stop.is_set():
            await self.refresh()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval)


def build_sources(settings: Settings) -> list[StartsSource]:
    """설정에 주소가 있는 받을 곳들. 주소가 없는 서버는 빠진다."""
    candidates = (
        (WorkKind.CHARACTER, settings.chat_url, settings.chat_server_secret),
        (WorkKind.WORLD, settings.story_url, settings.story_server_secret),
    )
    return [
        StartsSource(kind=kind, base_url=url, secret=secret.get_secret_value(), timeout=settings.stats_timeout_seconds)
        for kind, url, secret in candidates
        if url
    ]


def start(refresher: StartsRefresher) -> Running:
    """바퀴를 돌리기 시작한다. 서버가 뜰 때 부른다."""
    return loops.start(refresher, 'work-starts')
