# trpg-server/tests/test_job_limits.py

"""
뒤에서 도는 작업의 한도(app/core/jobs.py, app/core/job_setup.py, #275)를 검증한다. DB 도 서버도 쓰지 않는다.

넷을 본다.
  - 동시에 도는 수: 넘는 작업은 차례를 기다린다. 종류마다 따로 센다. 기다린 시간이 로그에 따로 남는다.
  - 상한: 돌거나 기다리는 수가 상한에 닿으면 맡지 않는다. 맡지 않은 작업은 닫히고 한 줄이 남는다.
  - 한 번만: 같은 이름의 작업이 돌거나 기다리면 맡지 않는다. 끝난 뒤에는 다시 맡는다.
  - 꺼질 때: 차례를 기다리던 작업은 시작하지 않은 채 닫힌다.
"""

import asyncio
import logging

import pytest

from app.core.config import Settings
from app.core.job_setup import job_limits
from app.core.jobs import DEFAULT_LIMIT, JOB_REFUSED_ERROR_CODE, BackgroundJobs, Limit
from app.lore import indexing as lore_indexing
from app.memory import indexing as memory_indexing
from app.rounds import closing
from tests.logs import rendered

JOBS_LOGGER = 'app.core.jobs'
NARRATE = 'round.narrate'
INDEX = 'lore.index'


class Gate:
    """테스트가 열어 줘야 끝나는 작업들. 몇 개가 동시에 돌고 있는지 센다."""

    def __init__(self) -> None:
        self.open = asyncio.Event()
        self.running = 0
        self.most = 0
        self.started: list[str] = []

    async def job(self, name: str) -> None:
        self.started.append(name)
        self.running += 1
        self.most = max(self.most, self.running)
        try:
            await self.open.wait()
        finally:
            self.running -= 1


async def settle() -> None:
    """맡긴 작업들이 시작할 수 있는 만큼 시작하게 한 바퀴 돌린다."""
    for _ in range(5):
        await asyncio.sleep(0)


# --- 한도 ---


@pytest.mark.parametrize(('concurrency', 'capacity'), [(0, 10), (3, 2)])
def test_a_limit_must_make_sense(concurrency: int, capacity: int):
    with pytest.raises(ValueError):
        Limit(concurrency, capacity)


def test_an_operation_without_its_own_limit_uses_the_default():
    jobs = BackgroundJobs({NARRATE: Limit(2, 5)})

    assert jobs.limit_of(NARRATE) == Limit(2, 5)
    assert jobs.limit_of('job.run') == DEFAULT_LIMIT


def test_the_settings_decide_how_many_run_at_once():
    settings = Settings(job_narration_concurrency=3, job_index_concurrency=1)

    assert job_limits(settings) == {
        closing.NARRATE_OPERATION: Limit(3, closing.NARRATION_CAPACITY),
        lore_indexing.INDEX_OPERATION: Limit(1, lore_indexing.INDEX_CAPACITY),
        memory_indexing.INDEX_OPERATION: Limit(1, memory_indexing.INDEX_CAPACITY),
    }


@pytest.mark.parametrize('field', ['job_narration_concurrency', 'job_index_concurrency'])
def test_at_least_one_runs_at_once(field: str):
    with pytest.raises(ValueError):
        Settings(**{field: 0})


# --- 동시에 도는 수 ---


async def test_jobs_beyond_the_concurrency_wait_their_turn():
    jobs = BackgroundJobs({NARRATE: Limit(2, 10)})
    gate = Gate()

    for number in range(1, 5):
        jobs.spawn(gate.job(f'서술 {number}'), name=f'narrate:{number}', operation=NARRATE)
    await settle()

    # 넷을 맡았지만 둘만 돈다. 나머지 둘은 기다린다. 기다리는 것도 센다
    assert (gate.started, jobs.count(NARRATE)) == (['서술 1', '서술 2'], 4)

    gate.open.set()
    await jobs.drain()

    # 기다리던 것도 차례가 오면 돈다. 한 번에 둘을 넘은 적이 없다
    assert (len(gate.started), gate.most, jobs.count()) == (4, 2, 0)


async def test_each_operation_has_its_own_turns():
    jobs = BackgroundJobs({NARRATE: Limit(1, 10), INDEX: Limit(1, 10)})
    gate = Gate()

    jobs.spawn(gate.job('서술'), name='narrate:1', operation=NARRATE)
    jobs.spawn(gate.job('색인'), name='index-lore:1', operation=INDEX)
    await settle()

    # 서술이 자리를 다 써도 색인은 제 차례로 돈다
    assert gate.started == ['서술', '색인']
    gate.open.set()
    await jobs.drain()


async def test_a_failed_job_gives_its_turn_to_the_next():
    jobs = BackgroundJobs({NARRATE: Limit(1, 10)})
    done = []

    async def broken() -> None:
        raise RuntimeError('서술자가 죽었다')

    async def next_one() -> None:
        done.append('다음')

    jobs.spawn(broken(), name='narrate:1', operation=NARRATE)
    jobs.spawn(next_one(), name='narrate:2', operation=NARRATE)
    await jobs.drain()

    assert done == ['다음']


async def test_the_wait_is_logged_apart_from_the_run(caplog: pytest.LogCaptureFixture):
    jobs = BackgroundJobs({NARRATE: Limit(1, 10)})

    async def slow() -> None:
        await asyncio.sleep(0.05)

    with caplog.at_level(logging.INFO, logger=JOBS_LOGGER):
        jobs.spawn(slow(), name='narrate:1', operation=NARRATE)
        jobs.spawn(slow(), name='narrate:2', operation=NARRATE)
        await jobs.drain()

    first, second = [line for line in rendered(caplog.records, JOBS_LOGGER) if line.get('result') == 'success']
    # 첫째는 기다리지 않았다. 둘째는 첫째가 끝날 때까지 기다렸다. 돈 시간은 기다린 시간과 따로 센다
    assert first['queue_ms'] < 40
    assert second['queue_ms'] >= 40
    assert second['duration_ms'] >= 40


# --- 상한 ---


async def test_a_full_operation_takes_no_more(caplog: pytest.LogCaptureFixture):
    jobs = BackgroundJobs({NARRATE: Limit(1, 2)})
    gate = Gate()
    jobs.spawn(gate.job('서술 1'), name='narrate:1', operation=NARRATE)
    jobs.spawn(gate.job('서술 2'), name='narrate:2', operation=NARRATE)
    third = gate.job('서술 3')

    with caplog.at_level(logging.WARNING, logger=JOBS_LOGGER):
        job_id = jobs.spawn(third, name='narrate:3', operation=NARRATE)

    # 맡지 않았다. 작업은 시작하지 않은 채 닫혔다(기다리지 않은 코루틴의 경고가 나지 않는다)
    assert (job_id, jobs.count(NARRATE), third.cr_frame) == (None, 2, None)
    (line,) = [line for line in rendered(caplog.records, JOBS_LOGGER) if line['level'] == 'warning']
    assert (line['operation'], line['job_name'], line['capacity'], line['error_code']) == (
        NARRATE,
        'narrate:3',
        2,
        JOB_REFUSED_ERROR_CODE,
    )
    gate.open.set()
    await jobs.drain()


async def test_a_full_operation_does_not_stop_the_others():
    jobs = BackgroundJobs({NARRATE: Limit(1, 1)})
    gate = Gate()
    jobs.spawn(gate.job('서술'), name='narrate:1', operation=NARRATE)

    assert jobs.spawn(gate.job('색인'), name='index-lore:1', operation=INDEX) is not None
    gate.open.set()
    await jobs.drain()


async def test_room_opens_again_when_a_job_ends():
    jobs = BackgroundJobs({NARRATE: Limit(1, 1)})

    async def quick() -> None:
        return None

    jobs.spawn(quick(), name='narrate:1', operation=NARRATE)
    await jobs.drain()

    assert jobs.spawn(quick(), name='narrate:2', operation=NARRATE) is not None
    await jobs.drain()


# --- 한 번만 ---


async def test_the_same_job_is_not_taken_twice_while_it_runs():
    jobs = BackgroundJobs()
    gate = Gate()
    first = jobs.spawn_once(gate.job('색인'), name='index-lore:판', operation=INDEX)
    again = gate.job('또 색인')

    second = jobs.spawn_once(again, name='index-lore:판', operation=INDEX)
    # 다른 판의 색인은 맡는다
    other = jobs.spawn_once(gate.job('다른 판'), name='index-lore:다른 판', operation=INDEX)

    assert first is not None and other is not None
    assert (second, again.cr_frame, jobs.count(INDEX)) == (None, None, 2)
    gate.open.set()
    await jobs.drain()


async def test_the_same_job_is_taken_again_after_it_ends():
    jobs = BackgroundJobs()

    async def quick() -> None:
        return None

    jobs.spawn_once(quick(), name='index-lore:판', operation=INDEX)
    await jobs.drain()

    assert jobs.spawn_once(quick(), name='index-lore:판', operation=INDEX) is not None
    await jobs.drain()


async def test_taking_once_still_respects_the_limit():
    jobs = BackgroundJobs({INDEX: Limit(1, 1)})
    gate = Gate()
    jobs.spawn_once(gate.job('색인'), name='index-lore:판', operation=INDEX)

    assert jobs.spawn_once(gate.job('다른 판'), name='index-lore:다른 판', operation=INDEX) is None
    gate.open.set()
    await jobs.drain()


# --- 꺼질 때 ---


async def test_closing_closes_the_jobs_still_waiting_their_turn(caplog: pytest.LogCaptureFixture):
    jobs = BackgroundJobs({NARRATE: Limit(1, 10)})
    gate = Gate()
    jobs.spawn(gate.job('도는 서술'), name='narrate:1', operation=NARRATE)
    waiting = gate.job('기다리는 서술')
    jobs.spawn(waiting, name='narrate:2', operation=NARRATE)
    await settle()

    with caplog.at_level(logging.WARNING, logger=JOBS_LOGGER):
        await jobs.aclose(grace=0.05)

    # 기다리던 작업은 시작하지 않은 채 닫혔다. 도는 작업도 취소됐다. 둘 다 한 줄씩 남는다
    assert (gate.started, waiting.cr_frame, jobs.count()) == (['도는 서술'], None, 0)
    lines = [line for line in rendered(caplog.records, JOBS_LOGGER) if 'result' in line]
    assert sorted((line['job_name'], line['result']) for line in lines) == [
        ('narrate:1', 'cancelled'),
        ('narrate:2', 'cancelled'),
    ]
    assert 'queue_ms' in next(line for line in lines if line['job_name'] == 'narrate:2')
