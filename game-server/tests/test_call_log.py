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
from app.ai.calls import CallRecord, CallScope, Outcome, input_digest
from app.ai.models import AiInvocation
from app.ai.provider import ChatMessage, Reasoning, Role

pytestmark = pytest.mark.usefixtures('clean_tables')

TABLE = uuid.UUID('aaaaaaaa-2222-4333-8444-555555555555')
HOST = uuid.UUID('11111111-2222-4333-8444-555555555555')
ENTRY = uuid.UUID('eeeeeeee-2222-4333-8444-555555555555')

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
    temperature=0.8,
    max_tokens=800,
    lore_entry_ids=(ENTRY,),
    memory_rounds=(3, 7),
    input_digest='ab' * 32,
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
    assert (row.temperature, row.max_tokens) == (0.8, 800)
    assert (row.lore_entry_ids, row.input_digest) == ([ENTRY], 'ab' * 32)
    assert row.memory_rounds == [3, 7]


async def test_the_log_saves_each_record_at_once(app: FastAPI, session: AsyncSession):
    log = DbCallLog(app.state.session_factory)

    await log.write(RECORD)
    await log.write(FAILED)

    # 쓸 때마다 바로 저장한다. 다른 세션(테스트의 세션)에서 보인다
    ok, failed = await stored(session)
    assert (ok.outcome, ok.text, ok.output_tokens) == ('ok', RECORD.text, 180)
    assert (failed.outcome, failed.error, failed.text) == ('failed', 'timeout', None)
    assert ok.id != failed.id
    assert (ok.lore_entry_ids, ok.max_tokens) == ([ENTRY], 800)


async def test_a_record_without_lore_stores_an_empty_list(app: FastAPI, session: AsyncSession):
    await DbCallLog(app.state.session_factory).write(replace(RECORD, lore_entry_ids=(), memory_rounds=()))

    (row,) = await stored(session)
    assert row.lore_entry_ids == []
    assert row.memory_rounds == []


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
        (replace(RECORD, max_tokens=0), 'max_tokens_positive'),
        (replace(RECORD, outcome='lost', error='lost'), 'outcome_allowed'),
    ],
)
async def test_the_database_refuses_a_record_that_does_not_add_up(
    session: AsyncSession, record: CallRecord, constraint: str
):
    session.add(to_row(record))

    with pytest.raises(IntegrityError, match=constraint):
        await session.commit()


# --- 입력의 지문 ---

MESSAGES = [
    ChatMessage(Role.SYSTEM, '너는 GM 이다. 악역영애는 사실 경찰의 끄나풀이다.'),
    ChatMessage(Role.USER, '달린다.'),
]


def test_the_digest_is_an_hmac_of_the_messages():
    digest = input_digest(MESSAGES, b'server-key')

    assert digest is not None
    assert len(digest) == 64
    # 같은 입력이면 같은 지문이다. 두 호출이 같은 입력이었는지 알 수 있다
    assert digest == input_digest(list(MESSAGES), b'server-key')


def test_a_different_message_or_key_gives_a_different_digest():
    changed = [MESSAGES[0], ChatMessage(Role.USER, '멈춘다.')]

    assert input_digest(changed, b'server-key') != input_digest(MESSAGES, b'server-key')
    # 키를 모르면 같은 입력으로도 지문을 맞출 수 없다. 내용을 대입해 확인하지 못한다
    assert input_digest(MESSAGES, b'other-key') != input_digest(MESSAGES, b'server-key')


def test_the_role_is_part_of_the_digest():
    as_assistant = [MESSAGES[0], ChatMessage(Role.ASSISTANT, '달린다.')]

    assert input_digest(as_assistant, b'server-key') != input_digest(MESSAGES, b'server-key')


@pytest.mark.parametrize('key', [None, b''])
def test_without_a_key_there_is_no_digest(key: bytes | None):
    assert input_digest(MESSAGES, key) is None
