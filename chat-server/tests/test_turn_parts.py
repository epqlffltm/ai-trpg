# chat-server/tests/test_turn_parts.py

"""
말 한 번의 작은 부품들. 결제 서버의 답을 이 서버의 뜻으로 바꾸기(app/turns/charging.py),
모델의 창구를 설정으로 만들기(app/turns/providers.py), 따로 도는 작업의 오류를 로그에 남기기(app/turns/router.py).
DB 를 쓰지 않는다.
"""

import asyncio
import logging
import uuid

import httpx
import pytest
from ai_core.routing import DEEPINFRA_KIND, OPENAI_KIND

from app.billing.client import BillingRejected, HoldOutcome, HoldResult
from app.turns import charging
from app.turns.charging import HoldDeclined
from app.turns.providers import build_router
from app.turns.router import log_failure
from tests.conftest import make_test_settings

USER = uuid.UUID('11111111-2222-4333-8444-555555555555')


class Refusing:
    """홀드를 받아들이지 않는 결제 서버."""

    def __init__(self, error: BillingRejected) -> None:
        self.error = error

    async def hold(self, reference: str, user_id: uuid.UUID, price_code: str) -> HoldOutcome:
        raise self.error


class Holding:
    """정해 둔 결과로 홀드를 거는 결제 서버."""

    def __init__(self, result: HoldResult) -> None:
        self.result = result

    async def hold(self, reference: str, user_id: uuid.UUID, price_code: str) -> HoldOutcome:
        return HoldOutcome(self.result)


@pytest.mark.parametrize(
    ('error', 'code', 'logged'),
    [
        (BillingRejected(400, 'price.not_for_sale'), 'model_unavailable', False),
        (BillingRejected(409), 'billing_unavailable', True),
    ],
)
async def test_a_refused_hold_is_declined(
    error: BillingRejected, code: str, logged: bool, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.ERROR, logger='app.turns.charging'), pytest.raises(HoldDeclined) as raised:
        await charging.place_hold(Refusing(error), 'chat:gen:x', USER, 'chat.luna.i0.o0')

    # 팔지 않는 것은 버그가 아니다. 다른 거절(같은 이름표가 어긋났다)은 사람이 보도록 남긴다
    assert raised.value.code == code
    assert bool([record for record in caplog.records if record.name == 'app.turns.charging']) is logged


async def test_a_hold_that_takes_returns_quietly():
    assert await charging.place_hold(Holding(HoldResult.HELD), 'chat:gen:x', USER, 'chat.luna.i0.o0') is None


def test_only_providers_with_a_key_are_opened():
    settings = make_test_settings(openai_api_key='sk-test', deepinfra_api_key='di-test')

    router = build_router(settings, httpx.AsyncClient(), session_factory=None)

    assert (router.openai.kind, router.openai.base_url) == (OPENAI_KIND, settings.openai_base_url)
    assert router.deepinfra.kind == DEEPINFRA_KIND
    assert (router.anthropic, router.gemini, router.zai) == (None, None, None)
    assert router.timeout == settings.llm_timeout_seconds


async def test_a_task_that_crashed_is_logged(caplog: pytest.LogCaptureFixture):
    async def crash() -> None:
        raise RuntimeError('버그')

    task = asyncio.create_task(crash())
    with pytest.raises(RuntimeError):
        await task

    with caplog.at_level(logging.ERROR, logger='app.turns.router'):
        log_failure(task)

    assert [record.getMessage() for record in caplog.records] == ['말 한 번의 작업이 오류로 끝났습니다']


async def test_a_cancelled_or_finished_task_is_not_logged(caplog: pytest.LogCaptureFixture):
    done = asyncio.create_task(asyncio.sleep(0))
    await done
    cancelled = asyncio.create_task(asyncio.sleep(10))
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    with caplog.at_level(logging.ERROR, logger='app.turns.router'):
        log_failure(done)
        log_failure(cancelled)

    assert caplog.records == []
