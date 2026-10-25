# story-server/app/billing/http_billing.py

"""
결제 서버를 실제로 부르는 것. 요청마다 서명하고(signing.py), 답을 결과나 예외로 바꾼다.

주소와 답의 뜻은 결제 서버가 정했다(billing-server/README.md 의 "홀드").

| 답 | 홀드 | 확정 | 반환 | 연장 |
| --- | --- | --- | --- | --- |
| 200, 201 | 잡혔다(HELD) | 됐다 | 됐다 | 됐다(EXTENDED) |
| 402 | 모자란다(SHORT) | - | - | - |
| 404 | 버그(BillingRejected) | 버그 | 걸린 적이 없다. 돌려줄 것도 없으니 됐다 | 홀드가 없다(MISSING) |
| 409 | 버그 | 이미 반대로 끝났다(만료되어 돌려준 것도). 버그로 본다 | 버그 | 이미 끝났다(ENDED) |
| 401, 408, 429, 5xx, 연결 실패, 시간 초과 | 다시 부를 일(BillingUnavailable) | 같다 | 같다 | 같다 |
| 그 밖의 4xx | 버그 | 버그 | 버그 | 버그 |

401 은 서명이 거절된 것이다. 설정을 고치면 낫는 일이라 다시 부를 일로 둔다(사람이 보도록 오류로 남는다).
200 인데 홀드의 상태가 기대와 다르면(같은 이름표의 홀드가 이미 반대로 끝났다) 버그다.

게임 서버의 것(trpg-server/app/billing/http_billing.py)과 같다.
서명은 공용 코드(server_core/service_auth/signing.py)로 한다. 추적의 머리말(traceparent)은
앱의 http 클라이언트(server_core 의 traced_client)가 싣는다. 결제 서버의 로그와 trace_id 로 이어진다.
"""

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import SecretStr
from server_core.service_auth.signing import SIGNATURE_HEADER, sign

from app.billing.client import (
    GOLD_REQUIRED_CODE,
    BillingRejected,
    BillingUnavailable,
    ExtendOutcome,
    ExtendResult,
    HoldOutcome,
    HoldResult,
)

HOLDS_PATH = '/api/v1/billing/service/holds'
CAPTURE_PATH = f'{HOLDS_PATH}/capture'
RELEASE_PATH = f'{HOLDS_PATH}/release'
EXTEND_PATH = f'{HOLDS_PATH}/extend'

# 다시 부르면 될 수 있는 답. 서명 거절(401), 시간 초과(408), 너무 많음(429)
RETRYABLE_CLIENT_ERRORS = frozenset({401, 408, 429})


def encode(payload: dict[str, str]) -> bytes:
    """보낼 본문. 이 바이트에 서명하고 이 바이트를 보낸다."""
    return json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode()


def unavailable_reason(status_code: int) -> str | None:
    """다시 부르면 될 수 있는 답이면 그 까닭의 이름. 아니면 None."""
    if status_code == 401:
        return 'unauthorized'
    if status_code >= 500 or status_code in RETRYABLE_CLIENT_ERRORS:
        return 'server_error'
    return None


def hold_status(response: httpx.Response) -> str:
    """홀드를 담은 답에서 홀드의 상태(held, captured, released). 본문을 읽을 수 없으면 BillingUnavailable."""
    try:
        body: Any = response.json()
        return str(body['status'])
    except (ValueError, KeyError, TypeError) as error:
        raise BillingUnavailable('bad_response') from error


def expires_at_of(response: httpx.Response) -> datetime | None:
    """
    홀드를 담은 답의 만료 시각(expires_at). 없거나 읽을 수 없으면 None.

    만료 시각이 없다고 실패로 보지 않는다. 시각을 모르면 부르는 쪽이 정해 둔 간격으로 연장한다.
    결제 서버는 UTC 로 준다(...Z). 시간대가 없으면 UTC 로 본다.
    """
    try:
        moment = datetime.fromisoformat(str(response.json()['expires_at']))
    except (ValueError, KeyError, TypeError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def amount_of(response: httpx.Response) -> str | None:
    """홀드를 담은 답의 값(amount). 없거나 읽을 수 없으면 None. 셈하지 않으니 글자 그대로 둔다."""
    try:
        amount = response.json()['amount']
    except (ValueError, KeyError, TypeError):
        return None
    return str(amount) if isinstance(amount, (str, int)) else None


def error_code_of(response: httpx.Response) -> str | None:
    """4xx 의 본문에 결제 서버가 붙인 오류의 이름(code). 없거나 읽을 수 없으면 None. 그 밖의 칸은 읽지 않는다."""
    try:
        code = response.json().get('code')
    except (ValueError, AttributeError):
        return None
    return code if isinstance(code, str) else None


def require_success(response: httpx.Response) -> None:
    """2xx 가 아니면 예외로 바꾼다. 다시 부를 일이면 BillingUnavailable, 아니면 BillingRejected(오류의 이름과 함께)."""
    if response.is_success:
        return
    reason = unavailable_reason(response.status_code)
    if reason is not None:
        raise BillingUnavailable(reason)
    raise BillingRejected(response.status_code, error_code_of(response))


def require_status(response: httpx.Response, expected: str) -> None:
    """성공한 답의 홀드가 expected 상태인지 본다. 아니면 BillingRejected(그 답의 상태 코드)."""
    if hold_status(response) != expected:
        raise BillingRejected(response.status_code)


def hold_result(response: httpx.Response) -> HoldOutcome:
    """
    홀드를 거는 요청의 답을 결과로 바꾼다. 잡혔으면 만료 시각을 함께 준다.

    402 는 크레딧이 모자란 것이다. 오류의 이름이 credit.gold_required 면 골드가 모자란 것으로 가른다.
    """
    if response.status_code == httpx.codes.PAYMENT_REQUIRED:
        if error_code_of(response) == GOLD_REQUIRED_CODE:
            return HoldOutcome(HoldResult.GOLD_REQUIRED)
        return HoldOutcome(HoldResult.SHORT)
    require_success(response)
    require_status(response, 'held')
    return HoldOutcome(HoldResult.HELD, expires_at_of(response), amount_of(response))


def capture_result(response: httpx.Response) -> None:
    """확정하는 요청의 답을 본다."""
    require_success(response)
    require_status(response, 'captured')


def release_result(response: httpx.Response) -> None:
    """돌려주는 요청의 답을 본다. 걸린 적이 없는 홀드(404)도 돌려줄 것이 없으니 된 것이다."""
    if response.status_code == httpx.codes.NOT_FOUND:
        return
    require_success(response)
    require_status(response, 'released')


def extend_result(response: httpx.Response) -> ExtendOutcome:
    """연장하는 요청의 답을 결과로 바꾼다. 연장했으면 새 만료 시각을 함께 준다."""
    if response.status_code == httpx.codes.NOT_FOUND:
        return ExtendOutcome(ExtendResult.MISSING)
    if response.status_code == httpx.codes.CONFLICT:
        return ExtendOutcome(ExtendResult.ENDED)
    require_success(response)
    require_status(response, 'held')
    return ExtendOutcome(ExtendResult.EXTENDED, expires_at_of(response))


@dataclass(frozen=True)
class HttpBilling:
    """
    결제 서버를 부르는 것. client 는 앱이 함께 쓰는 httpx 클라이언트다. 닫는 것은 앱이 한다.

    clock 은 서명에 적는 지금 시각(초)이다. 테스트가 시각을 정해 꽂는다.
    """

    client: httpx.AsyncClient
    base_url: str
    secret: SecretStr
    timeout: float
    clock: Callable[[], float] = time.time

    def headers_for(self, path: str, body: bytes) -> dict[str, str]:
        """보낼 머리말. 본문의 모양과 서명이다."""
        signature = sign(self.secret.get_secret_value(), int(self.clock()), 'POST', path, body)
        return {'Content-Type': 'application/json', SIGNATURE_HEADER: signature}

    async def post(self, path: str, payload: dict[str, str]) -> httpx.Response:
        """서명한 요청을 보내고 답을 돌려준다. 답을 받지 못하면 BillingUnavailable."""
        body = encode(payload)
        url = self.base_url.rstrip('/') + path
        try:
            return await self.client.post(url, content=body, headers=self.headers_for(path, body), timeout=self.timeout)
        except httpx.TimeoutException as error:
            raise BillingUnavailable('timeout') from error
        except httpx.HTTPError as error:
            raise BillingUnavailable('unreachable') from error

    async def hold(self, reference: str, user_id: uuid.UUID, price_code: str) -> HoldOutcome:
        payload = {'user_id': str(user_id), 'reference': reference, 'price_code': price_code}
        return hold_result(await self.post(HOLDS_PATH, payload))

    async def capture(self, reference: str) -> None:
        capture_result(await self.post(CAPTURE_PATH, {'reference': reference}))

    async def release(self, reference: str) -> None:
        release_result(await self.post(RELEASE_PATH, {'reference': reference}))

    async def extend(self, reference: str) -> ExtendOutcome:
        return extend_result(await self.post(EXTEND_PATH, {'reference': reference}))
