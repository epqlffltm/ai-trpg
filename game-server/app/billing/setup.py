# game-server/app/billing/setup.py

"""설정을 보고 결제 서버를 부르는 것을 만든다. 주소(BILLING_URL)가 비었으면 받지 않는 것이다."""

import httpx

from app.billing.client import Billing
from app.billing.free_billing import FreeBilling
from app.billing.http_billing import HttpBilling
from app.core.config import Settings


def build_billing(settings: Settings, http_client: httpx.AsyncClient) -> Billing:
    """결제 서버를 부르는 것. 앱이 함께 쓰는 http_client 로 부른다."""
    if not settings.billing_url.strip():
        return FreeBilling()
    return HttpBilling(
        client=http_client,
        base_url=settings.billing_url.strip(),
        secret=settings.billing_secret,
        timeout=settings.billing_timeout_seconds,
    )
