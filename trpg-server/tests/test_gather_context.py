# trpg-server/tests/test_gather_context.py

"""
서술 전에 넣을 것을 고르는 일(app/rounds/closing.py 의 gather_context)의 차례를 검증한다. DB 도 모델도 부르지 않는다.

  - 로어북을 먼저 고르고, 지난 일과 인물의 이력과 참고 자료는 로어북의 결과를 받아 함께 돈다
  - 하나가 실패하거나 시간이 다 되어도 나머지는 고른다
  - 전체와 하나하나가 걸린 시간을 메트릭으로 남긴다(#628). 하나하나에는 끝난 모양(success, timeout, failure)이 붙는다
"""

import asyncio
import logging
from dataclasses import dataclass, field

import pytest

from app.rounds.closing import Finders, gather_context
from app.rounds.narrator import Move, NarrationRequest, StoryContext
from tests.metrics import MetricsRecorder

REQUEST = NarrationRequest(
    round_number=1,
    scene='사이렌이 울린다.',
    moves=[Move('엘프', '달린다.')],
    story=StoryContext(title='추격전', rating='all', guide=''),
)
LORE = ['드워프']
# 넉넉한 시간. 함께 돌지 않으면 아래의 Meeting 이 이 안에 풀리지 않는다
BUDGET = 1.0


@dataclass
class Fixed:
    """늘 같은 것을 고르는 것. 받은 요청이 쌓인다."""

    found: list
    seen: list[NarrationRequest] = field(default_factory=list)

    async def find(self, request: NarrationRequest) -> list:
        self.seen.append(request)
        return self.found


@dataclass
class Meeting:
    """셋이 모두 와야 답하는 것. 차례로 돌면 첫째가 끝내 기다리다 시간이 다 된다."""

    barrier: asyncio.Barrier
    found: list

    async def find(self, request: NarrationRequest) -> list:
        await self.barrier.wait()
        return self.found


@dataclass
class Broken:
    async def find(self, request: NarrationRequest) -> list:
        raise RuntimeError('버그')


@dataclass
class Stuck:
    async def find(self, request: NarrationRequest) -> list:
        await asyncio.Event().wait()
        return []


async def test_the_three_after_the_lore_run_together():
    barrier = asyncio.Barrier(3)
    finders = Finders(
        lore=Fixed(LORE),
        memories=Meeting(barrier, ['지난 일']),
        histories=Meeting(barrier, ['이력']),
        references=Meeting(barrier, ['참고']),
    )

    request = await gather_context(REQUEST, finders, BUDGET)

    assert (request.memories, request.histories, request.references) == (['지난 일'], ['이력'], ['참고'])


async def test_the_others_see_what_the_lore_chose():
    histories, references = Fixed(['이력']), Fixed(['참고'])
    finders = Finders(lore=Fixed(LORE), histories=histories, references=references)

    request = await gather_context(REQUEST, finders, BUDGET)

    # 이력은 로어북이 고른 인물의 것이고, 참고 자료는 로어북이 쓰고 남은 자리에 들어간다
    assert request.lore == LORE
    assert [seen.lore for seen in histories.seen + references.seen] == [LORE, LORE]


async def test_one_failure_leaves_the_others(caplog: pytest.LogCaptureFixture):
    finders = Finders(lore=Fixed(LORE), memories=Broken(), histories=Fixed(['이력']), references=Fixed(['참고']))

    with caplog.at_level(logging.ERROR):
        request = await gather_context(REQUEST, finders, BUDGET)

    assert (request.memories, request.histories, request.references) == ([], ['이력'], ['참고'])
    assert '지난 일을 고르지 못했다' in caplog.text


async def test_one_that_runs_out_of_time_leaves_the_others(caplog: pytest.LogCaptureFixture):
    finders = Finders(lore=Fixed(LORE), memories=Fixed(['지난 일']), histories=Fixed(['이력']), references=Stuck())

    with caplog.at_level(logging.WARNING):
        request = await gather_context(REQUEST, finders, 0.05)

    assert (request.memories, request.histories, request.references) == (['지난 일'], ['이력'], [])
    assert '참고 자료를 고르는 데 시간이 다 됐다' in caplog.text


# --- 메트릭(#628) ---

PARTS = ('lore', 'memories', 'histories', 'references')


async def test_the_whole_and_each_part_are_timed(metrics: MetricsRecorder):
    finders = Finders(lore=Fixed(LORE), memories=Fixed([]), histories=Fixed(['이력']), references=Fixed(['참고']))

    await gather_context(REQUEST, finders, BUDGET)

    assert metrics.value('round_context_duration') == 1
    assert [metrics.value('round_context_part_duration', part=part, result='success') for part in PARTS] == [1] * 4
    (point,) = metrics.points('round_context_duration')
    assert point.unit == 's'


async def test_a_failure_and_a_timeout_are_told_apart(metrics: MetricsRecorder):
    finders = Finders(lore=Fixed(LORE), memories=Broken(), histories=Fixed(['이력']), references=Stuck())

    await gather_context(REQUEST, finders, 0.05)

    assert metrics.value('round_context_part_duration', part='memories', result='failure') == 1
    assert metrics.value('round_context_part_duration', part='references', result='timeout') == 1
    assert metrics.value('round_context_part_duration', part='histories', result='success') == 1
    # 고르지 못한 것이 있어도 전체는 잰다
    assert metrics.value('round_context_duration') == 1


async def test_a_cancelled_round_is_not_timed(metrics: MetricsRecorder):
    # 작업이 취소되면 그대로 올라간다. 끝나지 않은 일을 재지 않는다
    finders = Finders(lore=Stuck())
    task = asyncio.create_task(gather_context(REQUEST, finders, BUDGET))
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert metrics.points('round_context_duration') == []
    assert metrics.points('round_context_part_duration') == []
