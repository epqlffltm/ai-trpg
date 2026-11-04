# story-server/app/snapshots/pricing.py

"""
장면 그림 한 장의 값(#983). 화면이 "장면 그림" 단추 곁에 값을 보이고, 그릴 수 없으면 단추를 숨기게 한다.
DB 도 네트워크도 모르는 순수 함수다. 가격 목록은 결제 서버에서 받아 둔 것이다(app/billing/price_list.py).

  - 그림 provider 가 없으면(SNAPSHOT_PROVIDER 가 off 이거나 키가 없다) 그릴 수 없다
  - 결제 서버 없이 도는 서버(가격 목록이 free)면 그릴 수 있고 값이 없다
  - 가격 목록에 그 가격표 이름이 없거나 지금 팔지 않으면 그릴 수 없다. 예약된 바뀜의 시각이 지났으면 그 값이다
값은 보여 주는 것이다. 실제로 빠지는 값은 홀드를 걸 때 결제 서버가 그 시각의 가격표로 정한다.
"""

from datetime import datetime

from app.billing.prices import PriceBook, Sale, price_at
from app.snapshots.schemas import SnapshotPriceOut


def current_sale(book: PriceBook, price_code: str, now: datetime) -> Sale | None:
    """그 가격표 이름의 now 의 값. 없거나 팔지 않으면 None."""
    price = book.prices.get(price_code)
    return None if price is None else price_at(price, now).current


def snapshot_price(book: PriceBook, price_code: str, drawing_on: bool, now: datetime) -> SnapshotPriceOut:
    """장면 그림 한 장의 값과 그릴 수 있는지. drawing_on 은 그림 provider 가 있는지다."""
    if not drawing_on:
        return SnapshotPriceOut(available=False)
    if book.free:
        return SnapshotPriceOut(available=True)
    sale = current_sale(book, price_code, now)
    if sale is None:
        return SnapshotPriceOut(available=False)
    return SnapshotPriceOut(available=True, credits=sale.credits, tier=sale.tier, promo=sale.promo)
