# game-server/tests/test_call_log.py

"""
AI 호출의 기록을 DB 에 쓰는 기록장(app/ai/call_log.py)과 그 표(ai_invocations)를 검증한다.

보는 것은 셋이다.
  - 기록의 칸이 빠짐없이 한 줄로 들어간다.
  - 기록은 테이블에 묶이지 않는다. 없는 테이블의 호출도, 테이블 밖의 호출도 남는다.
  - 서로 맞지 않는 기록은 DB 가 막는다(잘 끝났는데 이유가 있다, 받지 못했는데 글이 있다 …).

모델을 부르지 않는다. 기록을 직접 만들어 넣는다. 서술자가 기록을 남기는지는 tests/test_llm_narrator.py 가 본다.
"""

import uuid
from dataclasses import replace

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.call_log import DbCallLog, to_row
from app.ai.calls import CallRecord, CallScope, Outcome
from app.ai.models import AiInvocation
from app.ai.provider import Reasoning

pytestmark = pytest.mark.usefixtures('clean_tables')

TABLE = uuid.UUID('aaaaaaaa-2222-4333-8444-555555555555')
HOST = uuid.UUID('11111111-2222-4333-8444-555555555555')

# 잘 끝난 서술 한 번. 칸을 빠짐없이 채웠다. 내용은 아무 뜻이 없다
RECORD = CallRecord(
    scope=CallScope(purpose='narration', table_id=TABLE, round_number=3, host_id=HOST),
    provider='openai_compat',
    model='gemma4:26b-a4b-it-qat',
    prompt_version='narration-3',
    reasoning=Reasoning.NONE,
    outcome=Outcome.OK,
    latency_ms=2400,
    narration_style='hardboiled',
    input_tokens=1050,
    output_tokens=180,
    finish_reason='stop',
    text='엔진 소리가 톨게이트를 메운다.',
)

# 받지 못한 호출. 글도 토큰도 없고 이유가 있다
FAILED = replace(
    RECORD,
    outcome=Outcome.FAILED,
    error='timeout',
    input_tokens=None,
    output_tokens=None,
    finish_reason=None,
    text=None,
)


async def stored(session: AsyncSession) -> list[AiInvocation]:
    """저장된 기록 전부. 저장한 순서다."""
    return list(await session.scalars(select(AiInvocation).order_by(AiInvocation.created_at)))


def test_a_record_becomes_a_row_with_every_field():
    row = to_row(RECORD)

    assert (row.purpose, row.table_id, row.round_number, row.host_id) == ('narration', TABLE, 3, HOST)
    assert (row.provider, row.model, row.prompt_version) == ('openai_compat', 'gemma4:26b-a4b-it-qat', 'narration-3')
    assert (row.reasoning, row.narration_style) == ('none', 'hardboiled')
    assert (row.outcome, row.error, row.latency_ms) == ('ok', None, 2400)
    assert (row.input_tokens, row.output_tokens, row.finish_reason) == (1050, 180, 'stop')
    assert row.text == RECORD.text


async def test_the_log_saves_each_record_at_once(app: FastAPI, session: AsyncSession):
    log = DbCallLog(app.state.session_factory)

    await log.write(RECORD)
    await log.write(FAILED)

    # 쓸 때마다 바로 저장한다. 다른 세션(테스트의 세션)에서 보인다
    ok, failed = await stored(session)
    assert (ok.outcome, ok.text, ok.output_tokens) == ('ok', RECORD.text, 180)
    assert (failed.outcome, failed.error, failed.text) == ('failed', 'timeout', None)
    assert ok.id != failed.id


async def test_a_record_does_not_need_the_table_to_exist(app: FastAPI, session: AsyncSession):
    outside = replace(RECORD, scope=CallScope(purpose='narration'))

    # 테이블에 외래 키가 없다. 지워진 테이블의 호출도, 테이블 밖의 호출도 남는다
    await DbCallLog(app.state.session_factory).write(RECORD)
    await DbCallLog(app.state.session_factory).write(outside)

    assert [row.table_id for row in await stored(session)] == [TABLE, None]


@pytest.mark.parametrize(
    ('record', 'constraint'),
    [
        # 잘 끝났는데 이유가 있다
        (replace(RECORD, error='cut_off'), 'error_unless_ok'),
        # 쓰지 않았는데 이유가 없다
        (replace(RECORD, outcome=Outcome.REJECTED), 'error_unless_ok'),
        # 받지 못했는데 글이 있다
        (replace(FAILED, text='어디서 왔나'), 'no_text_when_failed'),
        (replace(RECORD, latency_ms=-1), 'latency_not_negative'),
        (replace(RECORD, output_tokens=-5), 'tokens_not_negative'),
        (replace(RECORD, outcome='lost', error='lost'), 'outcome_allowed'),
    ],
)
async def test_the_database_refuses_a_record_that_does_not_add_up(
    session: AsyncSession, record: CallRecord, constraint: str
):
    session.add(to_row(record))

    with pytest.raises(IntegrityError, match=constraint):
        await session.commit()
