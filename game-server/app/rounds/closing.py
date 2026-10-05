# game-server/app/rounds/closing.py

"""
닫는 중인 라운드의 서술을 요청과 따로 돌린다.

라운드를 닫는 일은 둘로 나뉘어 있다(app/rounds/service.py). 닫기 시작과 닫기 마무리. 그 사이가 여기다.
  1. 닫는 중인 라운드를 읽는다.
  2. 서술자를 부른다. 이때는 잠금도 DB 연결도 쥐고 있지 않다.
  3. 닫기를 마무리한다.

이 작업은 끝까지 못 갈 수 있다. 서술자가 실패하거나, 도는 도중에 서버가 꺼진다.
그러면 라운드가 닫는 중에 머문다. 여기서 다시 시도하지 않는다. 방장이 닫기를 다시 눌러 맡긴다.
(자동으로 다시 시도하는 것과 다른 서술자로 넘어가는 것은 실제 AI 를 붙일 때 더한다.)
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.jobs import BackgroundJobs
from app.rounds import service
from app.rounds.narrator import Narrator


async def narrate_round(
    session_factory: async_sessionmaker[AsyncSession], narrator: Narrator, table_id: uuid.UUID, number: int
) -> None:
    """
    닫는 중인 라운드 하나를 서술하고 닫는다. 요청 밖에서 돈다.

    세션을 둘 따로 연다. 서술자를 기다리는 동안에는 어느 것도 열려 있지 않다.
    서술자가 예외를 내면 그대로 올린다. 작업을 돌리는 쪽(BackgroundJobs)이 로그에 남긴다.
    """
    async with session_factory() as session:
        request = await service.load_closing_request(session, table_id, number)
    if request is None:
        return

    scene = await narrator.narrate(request)

    async with session_factory() as session:
        await service.finish_closing(session, table_id, number, scene)


@dataclass(frozen=True)
class RoundCloser:
    """
    서술을 뒤에서 돌게 맡기는 것. service.NarrationScheduler 의 구현이다.

    요청마다 하나 만든다(app/rounds/router.py). 그때 앱에 꽂혀 있는 서술자를 쓴다.
    """

    session_factory: async_sessionmaker[AsyncSession]
    narrator: Narrator
    jobs: BackgroundJobs

    def schedule(self, table_id: uuid.UUID, number: int) -> None:
        """이 라운드의 서술을 맡긴다. 기다리지 않고 바로 돌아온다."""
        job = narrate_round(self.session_factory, self.narrator, table_id, number)
        self.jobs.spawn(job, name=f'narrate:{table_id}:{number}')
