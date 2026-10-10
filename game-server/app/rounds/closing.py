# game-server/app/rounds/closing.py

"""
닫는 중인 라운드의 서술을 요청과 따로 돌린다.

라운드를 닫는 일은 둘로 나뉘어 있다(app/rounds/service.py). 닫기 시작과 닫기 마무리. 그 사이가 여기다.
  1. 닫는 중인 라운드를 읽는다.
  2. 서술자를 부른다. 이때는 잠금도 DB 연결도 쥐고 있지 않다.
  3. 닫기를 마무리한다.

이 작업은 끝까지 못 갈 수 있다. 서술자가 실패하거나, 도는 도중에 서버가 꺼진다.
그러면 라운드가 닫는 중에 머문다. 방장이 닫기를 다시 눌러 맡긴다.
다시 시도하기와 다른 모델로 넘어가기는 서술자가 한다(app/rounds/retrying_narrator.py). 여기서는 다시 시도하지 않는다.

서술자가 쓰는 동안의 글은 미리 보기로 앉은 사람들에게 흘려보낸다(app/rounds/preview.py).
미리 보기를 닫은 뒤에 마무리하거나 실패를 적는다. 그래야 이벤트가 미리 보기의 마지막 조각보다 늦게 간다.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.provider import ProviderError
from app.core.jobs import BackgroundJobs
from app.rounds import service
from app.rounds.llm_narrator import NarrationError
from app.rounds.narrator import Narrator
from app.rounds.preview import notifier, open_preview
from app.rounds.retrying_narrator import NarrationFailed

# 서술자의 실패가 아닌 예외(버그)로 실패했을 때 이벤트에 적는 이유. 자세한 것은 로그에 남는다
UNEXPECTED = 'error'


def failure_reason(error: Exception) -> str:
    """
    서술자가 낸 예외에서 앉은 사람에게 알릴 실패의 이유를 꺼낸다.

    다시 시도하는 서술자는 마지막 이유를, 한 번 부르는 서술자는 그 이유를 준다.
    그 밖의 예외는 내용을 내보내지 않는다. 예외의 글에 무엇이 들어 있을지 모른다.
    """
    if isinstance(error, NarrationFailed):
        return error.reason
    if isinstance(error, ProviderError | NarrationError):
        return str(error)
    return UNEXPECTED


async def narrate_round(
    session_factory: async_sessionmaker[AsyncSession], narrator: Narrator, table_id: uuid.UUID, number: int
) -> None:
    """
    닫는 중인 라운드 하나를 서술하고 닫는다. 요청 밖에서 돈다.

    세션을 따로 연다. 서술자를 기다리는 동안에는 어느 세션도 열려 있지 않다.
    서술자가 끝내 실패하면 실패를 적고(앉은 사람 모두에게 알린다) 예외를 그대로 올린다.
    작업을 돌리는 쪽(BackgroundJobs)이 로그에 남긴다.
    서버가 꺼져 작업이 취소되면(CancelledError) 실패를 적지 않는다. 그때는 멈춘 라운드로 남는다.
    """
    async with session_factory() as session:
        request = await service.load_closing_request(session, table_id, number)
    if request is None:
        return

    try:
        async with open_preview(notifier(session_factory), table_id, number) as preview:
            scene = await narrator.narrate(request, preview)
    except Exception as error:
        async with session_factory() as session:
            await service.fail_closing(session, table_id, number, failure_reason(error))
        raise

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
