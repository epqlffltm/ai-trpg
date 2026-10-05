# game-server/tests/test_jobs.py

"""
요청과 따로 도는 작업(app/core/jobs.py)을 검증한다. DB 도 서버도 쓰지 않는다.

보는 것은 넷이다.
  - 맡기면 바로 돌아오고, 작업은 뒤에서 돈다.
  - 끝난 작업은 치워진다.
  - 실패한 작업은 로그에 남는다. 맡긴 쪽으로 예외가 올라오지 않는다.
  - 꺼질 때 남은 작업을 잠깐 기다렸다가 취소한다.
"""

import asyncio
import logging

import pytest

from app.core.jobs import BackgroundJobs


async def test_spawning_returns_at_once_and_the_job_runs_behind():
    jobs = BackgroundJobs()
    gate, done = asyncio.Event(), []

    async def job() -> None:
        await gate.wait()
        done.append('끝')

    jobs.spawn(job(), name='기다리는 작업')

    # 맡긴 쪽은 기다리지 않는다. 작업은 아직 끝나지 않았다
    assert (done, jobs.count()) == ([], 1)

    gate.set()
    await jobs.drain()

    assert (done, jobs.count()) == (['끝'], 0)


async def test_draining_also_waits_for_jobs_started_meanwhile():
    jobs = BackgroundJobs()
    done = []

    async def second() -> None:
        done.append('둘째')

    async def first() -> None:
        jobs.spawn(second(), name='둘째')
        done.append('첫째')

    jobs.spawn(first(), name='첫째')
    await jobs.drain()

    # 기다리는 동안 새로 시작된 작업도 끝난 뒤에 돌아온다
    assert sorted(done) == ['둘째', '첫째']
    assert jobs.count() == 0


async def test_a_failed_job_is_logged_and_does_not_raise(caplog: pytest.LogCaptureFixture):
    jobs = BackgroundJobs()

    async def job() -> None:
        raise RuntimeError('서술자가 죽었다')

    with caplog.at_level(logging.ERROR, logger='app.core.jobs'):
        jobs.spawn(job(), name='narrate:테이블:1')
        # 실패해도 기다리는 쪽으로 예외가 올라오지 않는다
        await jobs.drain()

    assert jobs.count() == 0
    (record,) = caplog.records
    # 어느 작업이 왜 실패했는지 남는다
    assert 'narrate:테이블:1' in record.getMessage()
    assert isinstance(record.exc_info[1], RuntimeError)


async def test_closing_waits_briefly_then_cancels_what_is_left():
    jobs = BackgroundJobs()
    finished, cancelled = [], []

    async def quick() -> None:
        await asyncio.sleep(0.01)
        finished.append('빠른 작업')

    async def endless() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append('끝나지 않는 작업')
            raise

    jobs.spawn(quick(), name='빠른 작업')
    jobs.spawn(endless(), name='끝나지 않는 작업')

    await jobs.aclose(grace=0.2)

    # 기다리는 시간 안에 끝난 것은 끝까지 하고, 남은 것은 취소한다
    assert (finished, cancelled) == (['빠른 작업'], ['끝나지 않는 작업'])
    assert jobs.count() == 0


async def test_closing_with_nothing_running_does_nothing():
    await BackgroundJobs().aclose()
