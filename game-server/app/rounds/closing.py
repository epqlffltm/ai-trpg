# game-server/app/rounds/closing.py

"""
닫는 중인 라운드의 서술을 요청과 따로 돌린다.

라운드를 닫는 일은 둘로 나뉘어 있다(app/rounds/service.py). 닫기 시작과 닫기 마무리. 그 사이가 여기다.
  1. 닫는 중인 라운드를 읽는다.
  2. 이번 장면에 맞는 로어북 항목(app/lore/retrieval.py)과 지난 일(app/memory/retrieval.py)을 고르고,
     로어북이 고른 인물의 이력을 모은다(app/memory/history.py). 고르지 못해도 서술은 한다.
  3. 서술자를 부른다. 이때는 잠금도 DB 연결도 쥐고 있지 않다.
  4. 닫기를 마무리한다.
로어북과 지난 일은 한 번 고르고, 다시 시도하는 모든 시도가 같은 것을 쓴다.

이 작업은 끝까지 못 갈 수 있다. 서술자가 실패하거나, 도는 도중에 서버가 꺼진다.
그러면 라운드가 닫는 중에 머문다. 방장이 닫기를 다시 눌러 맡긴다.
다시 시도하기와 다른 모델로 넘어가기는 서술자가 한다(app/rounds/retrying_narrator.py). 여기서는 다시 시도하지 않는다.

실패를 어디서 어떻게 받는가.
  - 1~4 를 통째로 감싼다. 어디서 예외가 나든 실패를 적고(앉은 사람 모두에게 알린다) 방장이 바로 다시 맡길 수 있다.
    감싸지 않은 곳에서 나면 로그만 남고 라운드는 한참 뒤에야 다시 맡길 수 있다.
  - 2 는 다르다. 고르기는 서술을 돕는 것이라 실패해도 서술을 막지 않는다. 예외가 나거나 시간이 다 되면
    로그에 남기고 고른 것 없이 서술한다. 고르기의 버그로 테이블이 영영 멈추는 것보다 설정이 빠진 서술이 낫다.
    임베딩 모델의 실패는 고르는 쪽이 이미 스스로 받는다. 여기서 받는 것은 그 밖의 예외(DB 의 오류, 버그)다.
  - 서버가 꺼져 작업이 취소되면(CancelledError) 실패를 적지 않는다. 그때는 멈춘 라운드로 남는다.

작업 전체에 시간의 상한이 있다(service.CLOSING_JOB_SECONDS). 닫기 시작한 시각(closing_at)부터 센다.
  - 방장이 다시 맡길 수 있는 때(service.CLOSING_RETRY_SECONDS)도 같은 시각부터 센다. 작업의 상한이 그보다 짧으므로
    "다시 맡길 수 있다"는 "앞서 맡은 작업은 끝났다"를 뜻한다. 서술 둘이 함께 도는 일이 없다.
  - 상한이 없으면 응답 없는 DB 연결이나 풀리지 않는 잠금을 하염없이 기다린다.
  - 시간이 다 되면 작업을 끊고 실패(timeout)를 적는다. 실패를 적는 데에도 따로 상한이 있다.

맡은 서술이 아직 지금의 것인지는 닫기 시작한 시각으로 안다(service.is_run). 다시 맡긴 뒤의 옛 작업은
라운드를 읽지도, 닫지도, 실패를 적지도 못한다. 마무리의 저장 도중에 끊겨도 마찬가지다. 실패를 적으려고
테이블을 잠그면 그 저장이 끝난 뒤의 상태를 읽고, 이미 닫혔으면 아무것도 적지 않는다.

서술자가 쓰는 동안의 글은 미리 보기로 앉은 사람들에게 흘려보낸다(app/rounds/preview.py).
미리 보기를 닫은 뒤에 마무리하거나 실패를 적는다. 그래야 이벤트가 미리 보기의 마지막 조각보다 늦게 간다.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.provider import ProviderError
from app.core.jobs import BackgroundJobs
from app.rounds import service
from app.rounds.llm_narrator import NarrationError
from app.rounds.narrator import LoreNote, MemoryNote, NarrationRequest, Narrator, PersonHistory
from app.rounds.preview import notifier, open_preview
from app.rounds.retrying_narrator import NarrationFailed

logger = logging.getLogger(__name__)

# 서술자의 실패가 아닌 예외(버그)로 실패했을 때 이벤트에 적는 이유. 자세한 것은 로그에 남는다
UNEXPECTED = 'error'
# 작업 전체의 시간이 다 됐을 때 이벤트에 적는 이유. 모델의 시간 초과와 같은 말을 쓴다
TIMED_OUT = 'timeout'


class LoreFinder(Protocol):
    """서술에 넣을 로어북 항목을 고르는 것. 구현은 app/lore/retrieval.py 의 LoreRetriever 다."""

    async def find(self, request: NarrationRequest) -> list[LoreNote]:
        """이번 장면에 맞는 항목들. 고를 것이 없으면 빈 목록이다."""
        ...


class NoLore:
    """아무것도 고르지 않는 것. 로어북 검색이 필요 없는 곳(테스트)에서 꽂는다."""

    async def find(self, request: NarrationRequest) -> list[LoreNote]:
        return []


NO_LORE = NoLore()


class MemoryFinder(Protocol):
    """서술에 넣을 지난 일을 고르는 것. 구현은 app/memory/retrieval.py 의 MemoryRetriever 다."""

    async def find(self, request: NarrationRequest) -> list[MemoryNote]:
        """이번 장면에 맞는 지난 일들. 고를 것이 없으면 빈 목록이다."""
        ...


class NoMemories:
    """아무것도 고르지 않는 것. 지난 일의 검색이 필요 없는 곳(테스트)에서 꽂는다."""

    async def find(self, request: NarrationRequest) -> list[MemoryNote]:
        return []


NO_MEMORIES = NoMemories()


class HistoryFinder(Protocol):
    """장면에 나온 인물의 이력을 모으는 것. 구현은 app/memory/history.py 의 HistoryCollector 다."""

    async def find(self, request: NarrationRequest) -> list[PersonHistory]:
        """로어북이 고른 인물들(request.lore)의 이력. 없으면 빈 목록이다."""
        ...


class NoHistories:
    """아무것도 모으지 않는 것. 이력이 필요 없는 곳(테스트)에서 꽂는다."""

    async def find(self, request: NarrationRequest) -> list[PersonHistory]:
        return []


NO_HISTORIES = NoHistories()


@dataclass(frozen=True)
class Run:
    """맡은 서술 하나. 어느 테이블의 몇 라운드를, 언제(닫기 시작한 시각) 맡았는가."""

    table_id: uuid.UUID
    number: int
    started: datetime


@dataclass(frozen=True)
class Finders:
    """서술에 넣을 것을 고르는 셋. 로어북, 지난 일, 인물의 이력."""

    lore: LoreFinder = NO_LORE
    memories: MemoryFinder = NO_MEMORIES
    histories: HistoryFinder = NO_HISTORIES


@dataclass(frozen=True)
class Budgets:
    """
    작업이 쓰는 시간(초). 값은 service 에 있다. 방장이 다시 맡길 수 있는 때와 함께 정해야 하는 숫자들이다.

    job 은 닫기 시작한 시각부터 작업이 끝날 때까지, retrieval 은 그중 고르기에, failure 는 끊긴 뒤 실패를 적는 데 쓴다.
    테스트가 짧은 시간을 꽂는다.
    """

    job: float = service.CLOSING_JOB_SECONDS
    retrieval: float = service.RETRIEVAL_BUDGET_SECONDS
    failure: float = service.FAILURE_RECORD_SECONDS


BUDGETS = Budgets()


def failure_reason(error: Exception) -> str:
    """
    작업을 실패시킨 예외에서 앉은 사람에게 알릴 실패의 이유를 꺼낸다.

    다시 시도하는 서술자는 마지막 이유를, 한 번 부르는 서술자는 그 이유를 준다. 작업의 시간이 다 됐으면 timeout 이다.
    그 밖의 예외는 내용을 내보내지 않는다. 예외의 글에 무엇이 들어 있을지 모른다.
    """
    if isinstance(error, NarrationFailed):
        return error.reason
    if isinstance(error, ProviderError | NarrationError):
        return str(error)
    if isinstance(error, TimeoutError):
        return TIMED_OUT
    return UNEXPECTED


def seconds_left(started: datetime, now: datetime, budget: float) -> float:
    """started 부터 budget 초를 쓸 수 있을 때 now 에 남은 시간(초). 이미 다 썼으면 0 이다."""
    return max(budget - (now - started).total_seconds(), 0.0)


async def find_or_nothing[Found](find: Callable[[], Awaitable[list[Found]]], deadline: float, what: str) -> list[Found]:
    """
    고르는 일 하나를 deadline(이벤트 루프의 시각)까지 해 본다. 예외가 나거나 시간이 다 되면 빈 목록이다.

    고르지 못해도 서술은 한다. 까닭은 로그에 남긴다. 버그라면 여기서 드러난다.
    작업이 취소된 것(CancelledError)은 받지 않는다. 그대로 올라간다.
    """
    try:
        async with asyncio.timeout_at(deadline):
            return await find()
    except TimeoutError:
        logger.warning('%s 고르는 데 시간이 다 됐다. 없이 서술한다', what)
    except Exception:
        logger.exception('%s 고르지 못했다. 없이 서술한다', what)
    return []


async def gather_context(request: NarrationRequest, finders: Finders, budget: float) -> NarrationRequest:
    """
    서술에 넣을 로어북 항목과 지난 일을 고르고 인물의 이력을 모아 요청에 싣는다. 셋을 합쳐 budget 초까지 쓴다.

    이력은 로어북이 고른 인물의 것이라 로어북을 먼저 고른다. 하나가 실패해도 나머지는 고른다.
    """
    deadline = asyncio.get_running_loop().time() + budget
    request = replace(request, lore=await find_or_nothing(lambda: finders.lore.find(request), deadline, '로어북을'))
    memories = await find_or_nothing(lambda: finders.memories.find(request), deadline, '지난 일을')
    histories = await find_or_nothing(lambda: finders.histories.find(request), deadline, '인물의 이력을')
    return replace(request, memories=memories, histories=histories)


async def write_scene(
    session_factory: async_sessionmaker[AsyncSession], narrator: Narrator, request: NarrationRequest, run: Run
) -> str:
    """서술자를 불러 장면을 받는다. 쓰는 동안의 글은 미리 보기로 흘려보낸다. 미리 보기를 닫은 뒤에 돌아온다."""
    async with open_preview(notifier(session_factory), run.table_id, run.number) as preview:
        return await narrator.narrate(request, preview)


async def close_run(
    session_factory: async_sessionmaker[AsyncSession], narrator: Narrator, run: Run, finders: Finders, retrieval: float
) -> None:
    """
    맡은 서술 하나를 처음부터 끝까지 한다. 읽고, 고르고, 서술하고, 닫기를 마무리한다.

    세션을 그때그때 따로 연다. 서술자를 기다리는 동안에는 어느 세션도 열려 있지 않다.
    읽었을 때 이 라운드가 이미 다른 서술을 기다리거나 닫혔으면 아무것도 하지 않는다.
    """
    async with session_factory() as session:
        request = await service.load_closing_request(session, run.table_id, run.number, run.started)
    if request is None:
        return
    request = await gather_context(request, finders, retrieval)
    scene = await write_scene(session_factory, narrator, request, run)
    async with session_factory() as session:
        await service.finish_closing(session, run.table_id, run.number, run.started, scene)


async def record_failure(
    session_factory: async_sessionmaker[AsyncSession], run: Run, reason: str, timeout: float
) -> None:
    """
    맡은 서술이 실패한 것을 적는다. timeout 초까지만 해 본다. 적지 못해도 예외를 올리지 않는다.

    DB 가 응답하지 않아 실패한 작업은 실패를 적는 것도 안 될 수 있다. 그때는 로그만 남는다.
    라운드는 닫는 중에 머물고, 방장은 한참 뒤에(service.CLOSING_RETRY_SECONDS) 다시 맡길 수 있다.
    세션을 새로 연다. 실패한 세션은 쓰지 않는다.
    """
    try:
        async with asyncio.timeout(timeout):
            async with session_factory() as session:
                await service.fail_closing(session, run.table_id, run.number, run.started, reason)
    except Exception:
        logger.exception('서술의 실패를 적지 못했다(테이블 %s, %s 라운드)', run.table_id, run.number)


async def narrate_round(
    session_factory: async_sessionmaker[AsyncSession],
    narrator: Narrator,
    table_id: uuid.UUID,
    number: int,
    started: datetime,
    lore: LoreFinder = NO_LORE,
    memories: MemoryFinder = NO_MEMORIES,
    histories: HistoryFinder = NO_HISTORIES,
    budgets: Budgets = BUDGETS,
) -> None:
    """
    닫는 중인 라운드 하나를 서술하고 닫는다. 요청 밖에서 돈다.

    started 는 이 서술을 맡기며 적은 닫기 시작한 시각이다. 그때부터 budgets.job 초 안에 끝낸다.
    넘으면 하던 일을 끊고 실패(timeout)를 적는다. 맡긴 뒤에 오래 기다렸다가 돌기 시작했으면 그만큼 덜 쓴다.

    어디서든 예외가 나면 실패를 적고 예외를 그대로 올린다. 작업을 돌리는 쪽(BackgroundJobs)이 로그에 남긴다.
    마무리의 저장이 끝난 뒤에 난 예외는 실패로 적히지 않는다. 이미 닫힌 라운드에는 실패를 적지 않는다.
    서버가 꺼져 작업이 취소되면(CancelledError) 실패를 적지 않는다. 그때는 멈춘 라운드로 남는다.
    """
    run = Run(table_id, number, started)
    finders = Finders(lore, memories, histories)
    try:
        async with asyncio.timeout(seconds_left(started, datetime.now(UTC), budgets.job)):
            await close_run(session_factory, narrator, run, finders, budgets.retrieval)
    except Exception as error:
        await record_failure(session_factory, run, failure_reason(error), budgets.failure)
        raise


@dataclass(frozen=True)
class RoundCloser:
    """
    서술을 뒤에서 돌게 맡기는 것. service.NarrationScheduler 의 구현이다.

    요청마다 하나 만든다(app/rounds/router.py). 그때 앱에 꽂혀 있는 서술자를 쓴다.
    """

    session_factory: async_sessionmaker[AsyncSession]
    narrator: Narrator
    jobs: BackgroundJobs
    lore: LoreFinder = NO_LORE
    memories: MemoryFinder = NO_MEMORIES
    histories: HistoryFinder = NO_HISTORIES

    def schedule(self, table_id: uuid.UUID, number: int, started: datetime) -> None:
        """이 라운드의 서술을 맡긴다. 기다리지 않고 바로 돌아온다. started 는 저장한 닫기 시작한 시각이다."""
        job = narrate_round(
            self.session_factory, self.narrator, table_id, number, started, self.lore, self.memories, self.histories
        )
        self.jobs.spawn(job, name=f'narrate:{table_id}:{number}')
