# game-server/tests/billing.py

"""
가짜 결제 서버. 홀드를 걸고, 확정하고, 돌려주고, 연장하는 네 주소를 결제 서버의 규칙대로 흉내 낸다
(billing-server/README.md 의 "홀드").

서명을 확인한다. 앱의 서명 코드(app/billing/signing.py)를 쓰지 않고 여기서 따로 계산한다.
같은 코드로 만들고 확인하면 둘이 함께 틀려도 통과한다.
앱의 서명이 결제 서버(Go)와 같은지는 tests/test_billing_client.py 가 결제 서버의 코드로 만든 값과 견줘 본다.

사용자마다 크레딧(balances)을 두고, 홀드를 걸면 빼고, 돌려주면 되돌린다. 테스트가 크레딧을 바꿔 충전을 흉내 낸다.
down 을 켜면 죽은 것이다. 연결하지 못한다.
expire 는 결제 서버의 정리 작업이 만료된 홀드를 돌려준 것을 흉내 낸다. extended 는 연장을 부른 이름표들이다.
"""

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import SecretStr

from app.billing.http_billing import HttpBilling

BILLING_URL = 'http://billing.test'
SECRET = 'test-billing-secret-0123456789abcdef'
PRICES = {'narration.standard': 50, 'narration.premium': 120}
# 결제 서버가 받아 주는 시각의 차이(초)
TOLERANCE = 300
# 홀드가 걸리거나 연장된 뒤 만료될 때까지(결제 서버의 HOLD_TTL 기본값)
HOLD_TTL = timedelta(hours=24)


def utc_now() -> datetime:
    """지금 시각(UTC)."""
    return datetime.now(UTC)


@dataclass
class FakeHold:
    """가짜 결제 서버의 홀드 하나."""

    user_id: str
    price_code: str
    amount: int
    expires_at: datetime
    status: str = 'held'


@dataclass
class FakeBillingServer:
    """
    가짜 결제 서버. 무엇을 불렀는지 calls 에 (주소의 끝, 이름표) 로 적는다. 받은 머리말은 headers 에 남긴다.
    """

    secret: str = SECRET
    balances: dict[uuid.UUID, int] = field(default_factory=dict)
    holds: dict[str, FakeHold] = field(default_factory=dict)
    down: bool = False
    calls: list[tuple[str, str]] = field(default_factory=list)
    extended: list[str] = field(default_factory=list)
    headers: list[httpx.Headers] = field(default_factory=list)
    # 판매를 멈춘 가격표 이름들(400 price.not_for_sale)
    not_for_sale: set[str] = field(default_factory=set)
    # 골드로만 내는 가격표 이름들(프리미엄)과 골드가 있는 사람들. 없으면 402 credit.gold_required
    gold_only: set[str] = field(default_factory=set)
    gold: set[uuid.UUID] = field(default_factory=set)
    # 만료 시각을 정하는 시계와 HOLD_TTL. 테스트가 바꿔 꽂는다
    clock: Callable[[], datetime] = utc_now
    ttl: timedelta = HOLD_TTL

    def signed(self, request: httpx.Request) -> bool:
        """머리말의 서명이 이 요청의 것이고 방금 만든 것인가."""
        header = request.headers.get('X-Service-Signature', '')
        parts = dict(part.split('=', 1) for part in header.split(',') if '=' in part)
        sent_at = parts.get('t', '')
        content = f'{sent_at}.{request.method}\n{request.url.raw_path.decode()}\n'.encode() + request.content
        expected = hmac.new(self.secret.encode(), content, hashlib.sha256).hexdigest()
        fresh = sent_at.isdigit() and abs(time.time() - int(sent_at)) <= TOLERANCE
        return fresh and hmac.compare_digest(parts.get('v1', ''), expected)

    def answer(self, status_code: int, reference: str = '', code: str | None = None) -> httpx.Response:
        """홀드를 담은 답. 홀드가 없으면 상태 코드만. 4xx 면 결제 서버처럼 오류의 이름(code)을 싣는다."""
        hold = self.holds.get(reference)
        if hold is None or status_code >= 300:
            body = {'detail': '...', **({'code': code} if code else {})}
            return httpx.Response(status_code, json=body)
        body = {
            'reference': reference,
            'user_id': hold.user_id,
            'amount': str(hold.amount),
            'status': hold.status,
            'expires_at': hold.expires_at.isoformat().replace('+00:00', 'Z'),
        }
        return httpx.Response(status_code, json=body)

    def place(self, body: dict) -> httpx.Response:
        """홀드를 건다. 같은 이름표면 걸어 둔 것을 돌려준다. 가격표에 없는 이름이면 400 이다."""
        reference, user_id, price_code = body['reference'], body['user_id'], body['price_code']
        existing = self.holds.get(reference)
        if existing is not None:
            same = (existing.user_id, existing.price_code) == (user_id, price_code)
            return self.answer(200, reference) if same else self.answer(409)
        if price_code not in PRICES:
            return self.answer(400, code='price.unknown')
        if price_code in self.not_for_sale:
            return self.answer(400, code='price.not_for_sale')
        if price_code in self.gold_only and uuid.UUID(user_id) not in self.gold:
            return self.answer(402, code='credit.gold_required')
        amount = PRICES[price_code]
        balance = self.balances.get(uuid.UUID(user_id), 0)
        if balance < amount:
            return self.answer(402, code='credit.insufficient')
        self.balances[uuid.UUID(user_id)] = balance - amount
        self.holds[reference] = FakeHold(user_id, price_code, amount, self.clock() + self.ttl)
        return self.answer(201, reference)

    def capture(self, reference: str) -> httpx.Response:
        """홀드를 확정한다."""
        hold = self.holds.get(reference)
        if hold is None:
            return self.answer(404)
        if hold.status == 'released':
            return self.answer(409)
        hold.status = 'captured'
        return self.answer(200, reference)

    def release(self, reference: str) -> httpx.Response:
        """홀드를 돌려준다. 크레딧이 돌아간다."""
        hold = self.holds.get(reference)
        if hold is None:
            return self.answer(404)
        if hold.status == 'captured':
            return self.answer(409)
        if hold.status == 'held':
            hold.status = 'released'
            user = uuid.UUID(hold.user_id)
            self.balances[user] = self.balances.get(user, 0) + hold.amount
        return self.answer(200, reference)

    def extend(self, reference: str) -> httpx.Response:
        """홀드의 만료를 민다. 없으면 404, 이미 끝났으면 409."""
        hold = self.holds.get(reference)
        if hold is None:
            return self.answer(404)
        if hold.status != 'held':
            return self.answer(409)
        self.extended.append(reference)
        hold.expires_at = self.clock() + self.ttl
        return self.answer(200, reference)

    def expire(self, reference: str) -> None:
        """정리 작업이 만료된 홀드를 돌려준 것. 크레딧이 돌아간다."""
        self.release(reference)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        """요청 하나에 답한다. httpx 가 네트워크 대신 이 함수를 부른다."""
        await asyncio.sleep(0)
        if self.down:
            raise httpx.ConnectError('연결할 수 없다', request=request)
        self.headers.append(request.headers)
        if not self.signed(request):
            return self.answer(401)
        body = json.loads(request.content)
        action = request.url.path.rsplit('/', 1)[-1]
        self.calls.append((action, body['reference']))
        if action == 'holds':
            return self.place(body)
        if action == 'capture':
            return self.capture(body['reference'])
        if action == 'extend':
            return self.extend(body['reference'])
        return self.release(body['reference'])

    def make_client(self) -> httpx.AsyncClient:
        """이 가짜 서버로 요청이 가는 클라이언트."""
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def billing(self, client: httpx.AsyncClient) -> HttpBilling:
        """이 가짜 서버를 부르는 앱의 실제 구현. client 는 make_client 로 만든 것이다."""
        return HttpBilling(client=client, base_url=BILLING_URL, secret=SecretStr(SECRET), timeout=5.0)

    def balance(self, user_id: uuid.UUID) -> int:
        """사용자의 크레딧."""
        return self.balances.get(user_id, 0)

    def statuses(self) -> dict[str, str]:
        """이름표마다 홀드의 상태."""
        return {reference: hold.status for reference, hold in self.holds.items()}
