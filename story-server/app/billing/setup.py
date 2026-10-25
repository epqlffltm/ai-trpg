# story-server/app/billing/setup.py

"""
설정을 보고 결제 서버를 부르는 것과 가격 목록을 받는 것을 만든다.

주소(BILLING_URL)가 있으면 결제 서버를 부르는 것을 세는 것(metered.py)으로 감싼다.
주소(BILLING_URL)가 비었으면 받지 않는 것이다. 홀드를 걸지 않고(FreeBilling), 가격 목록에도 값이 없다(FreePriceList).
"""

import httpx

from app.billing.client import Billing
from app.billing.free_billing import FreeBilling
from app.billing.http_billing import HttpBilling
from app.billing.metered import MeteredBilling
from app.billing.price_list import FreePriceList, HttpPriceList, PriceList
from app.core.config import Settings


def build_billing(settings: Settings, http_client: httpx.AsyncClient) -> Billing:
    """결제 서버를 부르는 것. 앱이 함께 쓰는 http_client 로 부른다. 부를 때마다 센다(MeteredBilling)."""
    if not settings.billing_url.strip():
        return FreeBilling()
    return MeteredBilling(
        HttpBilling(
            client=http_client,
            base_url=settings.billing_url.strip(),
            secret=settings.billing_secret,
            timeout=settings.billing_timeout_seconds,
        )
    )


def build_price_list(settings: Settings, http_client: httpx.AsyncClient) -> PriceList:
    """결제 서버의 가격 목록을 받아 두는 것. 홀드와 같은 주소, 같은 비밀, 같은 시간 상한이다."""
    if not settings.billing_url.strip():
        return FreePriceList()
    return HttpPriceList(
        client=http_client,
        base_url=settings.billing_url.strip(),
        secret=settings.billing_secret,
        timeout=settings.billing_timeout_seconds,
    )
