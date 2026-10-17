# game-server/tests/test_ai_log_retention.py

"""
AI 호출의 기록에 남은 원문을 보관 기간이 지나면 비우는 것(app/ai/retention.py, #274)을 검증한다.

정리 작업의 "지금"은 테스트가 정한다. 기록의 남긴 시각도 테스트가 적는다.

넷을 본다.
  - 비우기: 보관 기간이 지난 원문만 비운다. 줄과 그 밖의 칸(모델, 토큰 수, 결과)은 남는다. 기간 안의 원문은 그대로다.
  - 나눠 비우기: 한 묶음씩, 한 바퀴에 정해 둔 묶음까지만. 밀린 것은 다음 바퀴에 마저 비운다.
  - 기록: 비운 것이 있으면 info, 없으면 debug 한 줄. 비운 수가 실린다.
  - 설정: 기본 30일, 하루보다 짧게 할 수 없다. 앱에 기간이 꽂힌다.
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import retention
from app.ai.models import AiInvocation
from app.ai.retention import PRUNE_OPERATION, AiLogPruner, cutoff
from app.core.config import Settings
from tests.logs import rendered

pytestmark = pytest.mark.usefixtures('clean_tables')

# 이 테스트들의 "지금". 실제 시계를 읽지 않는다
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
RETENTION_DAYS = 30
RETENTION_LOGGER = 'app.ai.retention'


def pruner_of(app: FastAPI) -> AiLogPruner:
    """지금이 NOW 이고 30일 두는 정리 작업."""
    return AiLogPruner(app.state.session_factory, RETENTION_DAYS, clock=lambda: NOW)


async def add_call(session: AsyncSession, days_ago: float, text: str | None = '모델이 쓴 장면') -> AiInvocation:
    """days_ago 일 전에 남긴 서술 호출 하나를 적는다."""
    row = AiInvocation(
        purpose='narration',
        provider='fake',
        model='gemma',
        prompt_version='narration-27',
        reasoning='none',
        outcome='ok',
        latency_ms=1200,
        input_tokens=900,
        output_tokens=300,
        text=text,
        created_at=NOW - timedelta(days=days_ago),
    )
    session.add(row)
    await session.commit()
    return row


async def texts(app: FastAPI) -> list[str | None]:
    """기록들의 원문. 남긴 시각 순서다."""
    async with app.state.session_factory() as session:
        query = select(AiInvocation.text).order_by(AiInvocation.created_at)
        return list(await session.scalars(query))


# --- 비우기 ---


async def test_old_texts_are_cleared_and_recent_ones_kept(app: FastAPI, session: AsyncSession):
    await add_call(session, days_ago=45, text='오래된 장면')
    await add_call(session, days_ago=31, text='한 달 지난 장면')
    await add_call(session, days_ago=2, text='어제의 장면')

    cleared = await pruner_of(app).tick()

    assert cleared == 2
    assert await texts(app) == [None, None, '어제의 장면']


async def test_only_the_text_is_cleared(app: FastAPI, session: AsyncSession):
    await add_call(session, days_ago=45)

    await pruner_of(app).tick()

    async with app.state.session_factory() as fresh:
        row = await fresh.scalar(select(AiInvocation))
    # 줄은 남는다. 모델과 토큰 수와 결과는 원가를 재는 근거다
    assert row.text is None
    assert (row.model, row.input_tokens, row.output_tokens, row.outcome, row.latency_ms) == (
        'gemma',
        900,
        300,
        'ok',
        1200,
    )


async def test_a_text_right_at_the_limit_is_kept(app: FastAPI, session: AsyncSession):
    await add_call(session, days_ago=RETENTION_DAYS, text='딱 30일')

    assert await pruner_of(app).tick() == 0
    assert await texts(app) == ['딱 30일']


async def test_calls_without_text_are_not_counted(app: FastAPI, session: AsyncSession):
    await add_call(session, days_ago=45, text=None)

    assert await pruner_of(app).tick() == 0


async def test_clearing_twice_clears_nothing_more(app: FastAPI, session: AsyncSession):
    await add_call(session, days_ago=45)
    pruner = pruner_of(app)

    await pruner.tick()

    assert await pruner.tick() == 0


def test_the_cutoff_is_the_retention_before_now():
    assert cutoff(NOW, 30) == datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


# --- 나눠 비우기 ---


async def test_a_round_clears_a_bounded_number_of_batches(
    app: FastAPI, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(retention, 'PRUNE_BATCH', 2)
    monkeypatch.setattr(retention, 'PRUNE_MAX_BATCHES', 2)
    for days in range(40, 45):
        await add_call(session, days_ago=days)
    pruner = pruner_of(app)

    # 한 바퀴에 2 개씩 2 묶음. 밀린 하나는 다음 바퀴에 비운다. 오래된 것부터다
    assert await pruner.tick() == 4
    assert await texts(app) == [None, None, None, None, '모델이 쓴 장면']
    assert await pruner.tick() == 1


# --- 기록 ---


async def test_a_round_that_cleared_something_leaves_an_info_line(
    app: FastAPI, session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    await add_call(session, days_ago=45)

    with caplog.at_level(logging.DEBUG, logger=RETENTION_LOGGER):
        await pruner_of(app).tick()

    (line,) = rendered(caplog.records, RETENTION_LOGGER)
    assert line['level'] == 'info'
    assert (line['operation'], line['cleared'], line['retention_days'], line['result']) == (
        PRUNE_OPERATION,
        1,
        RETENTION_DAYS,
        'success',
    )
    assert 'job_id' in line


async def test_a_quiet_round_leaves_a_debug_line(app: FastAPI, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.DEBUG, logger=RETENTION_LOGGER):
        await pruner_of(app).tick()

    (line,) = rendered(caplog.records, RETENTION_LOGGER)
    assert (line['level'], line['cleared']) == ('debug', 0)


# --- 설정 ---


def test_the_texts_are_kept_thirty_days_by_default():
    assert Settings().ai_log_text_retention_days == 30


def test_the_retention_is_at_least_a_day():
    with pytest.raises(ValueError):
        Settings(ai_log_text_retention_days=0)


def test_the_app_prunes_with_the_set_retention(app: FastAPI, settings: Settings):
    assert app.state.ai_log_pruner.retention_days == settings.ai_log_text_retention_days
