# trpg-server/app/snapshots/pricing.py

"""
장면 그림 한 장의 값(#983). 화면이 "장면 그림" 단추 곁에 값을 보이고, 그릴 수 없으면 단추를 숨기게 한다.
DB 도 네트워크도 모르는 순수 함수다. 가격 목록은 결제 서버에서 받아 둔 것이다(server_core/billing/price_list.py).

그릴 수 있는가와 값을 정하는 규칙은 게임, chat, story 가 함께 쓰는 공용 코드에 있다(server_core/billing/prices.py 의
offer_of, #1266). 여기는 그것을 이 서버의 응답 모양(SnapshotPriceOut)으로 옮긴다.
값은 보여 주는 것이다. 실제로 빠지는 값은 홀드를 걸 때 결제 서버가 그 시각의 가격표로 정한다.
"""

from datetime import datetime

from server_core.billing.prices import PriceBook, offer_of

from app.snapshots.schemas import SnapshotPriceOut


def snapshot_price(book: PriceBook, price_code: str, drawing_on: bool, now: datetime) -> SnapshotPriceOut:
    """장면 그림 한 장의 값과 그릴 수 있는지. drawing_on 은 그림 provider 가 있는지다."""
    offer = offer_of(book, price_code, drawing_on, now)
    if offer.sale is None:
        return SnapshotPriceOut(available=offer.available)
    return SnapshotPriceOut(available=True, credits=offer.sale.credits, tier=offer.sale.tier, promo=offer.sale.promo)
