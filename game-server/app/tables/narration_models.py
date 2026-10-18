# game-server/app/tables/narration_models.py

"""
테이블의 서술 모델을 바꾼다. 방장만 한다.

모델은 라운드를 열 때 그 라운드의 것으로 굳는다(app/rounds/opener.py). 바꾼 값은 다음 라운드부터 쓴다.
다만 지금 라운드가 아직 서술되지 않았고 서술이 돌고 있지도 않으면 그 라운드의 모델도 함께 바꾼다.
  - 선언을 받는 중인 라운드
  - 서술이 실패해 멈춘 라운드(닫는 중, 실패를 적었다)
판매를 멈춘 모델이나 골드가 모자란 사람 때문에 막힌 라운드를 방장이 풀 수 있게 하려는 것이다.
그 라운드의 청구는 새 모델의 가격표로 다시 건다(app/billing/charges.py 의 reprice_round). 옛 홀드는 돌려준다.
서술이 돌고 있는 라운드는 바꾸지 않는다. 연 때의 모델의 값을 걸어 두었고 그 모델로 서술하는 중이다.

고를 수 있는 모델만 된다(app/tables/model_picker.py). 비울 수 없다. 서버의 기본 모델로 돌아가는 길은 없다.
바꾼 것은 이벤트로 남긴다. 지금 라운드에도 적용했으면 그 번호를 싣는다. 각자 값을 내므로 모두가 알아야 한다.

HTTP 를 모른다. 테이블을 잠그고 한다.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import charges
from app.catalog.offers import OfferedModel
from app.events import recorder
from app.events.models import EventType
from app.rounds import repository as round_repository
from app.rounds.models import Round, RoundStatus
from app.rounds.round_price import announce, price_payload
from app.tables.model_picker import ModelPicker, require_pickable
from app.tables.models import GameTable
from app.tables.schemas import NarrationModelUpdate
from app.tables.service import lock_seated, save
from app.tables.state import require_host, require_not_ended


def takes_new_model(round_: Round | None) -> bool:
    """이 라운드의 모델도 지금 바꿀 수 있는가. 선언을 받는 중이거나, 서술이 실패해 멈췄다."""
    if round_ is None:
        return False
    if round_.status == RoundStatus.OPEN:
        return True
    return round_.status == RoundStatus.CLOSING and round_.narration_failed_at is not None


def is_unchanged(table: GameTable, round_: Round | None, model: str) -> bool:
    """바꿀 것이 없는가. 테이블의 모델이 같고, 지금 바꿀 수 있는 라운드가 있으면 그 라운드의 모델도 같다."""
    if table.narration_model != model:
        return False
    return not takes_new_model(round_) or round_.narration_model == model


def forget_retire_notices(table: GameTable) -> None:
    """은퇴를 알린 것을 지운다. 모델이 바뀌면 새 모델의 은퇴일로 처음부터 다시 센다(app/tables/model_retirement.py)."""
    table.retire_notice_for = None
    table.retire_notice_days = None


async def apply_to_round(session: AsyncSession, round_: Round, model: str, price: OfferedModel | None) -> None:
    """
    라운드의 모델을 바꾸고, 그 라운드의 청구를 새 가격표로 다시 걸게 적는다.

    price 는 새 모델의 지금 값이다. 라운드에 알린 값도 바꾼다(app/rounds/round_price.py).
    """
    round_.narration_model = model
    announce(round_, price)
    await charges.reprice_round(session, round_, datetime.now(UTC))


async def change_narration_model(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, data: NarrationModelUpdate, picker: ModelPicker
) -> GameTable:
    """
    방장이 서술 모델을 바꾼다. 지금 라운드가 바꿀 수 있는 라운드면(takes_new_model) 그 라운드에도 적용한다.

    방장이 아니면 NotHostError, 끝난 테이블이면 TableConflictError, 고를 수 없는 모델이면 TableOptionError.
    바꿀 것이 없으면 아무것도 적지 않는다. 바뀐 것이 없는데 이벤트가 쌓이지 않게 한다.
    고를 수 있는지는 잠근 뒤, 값이 바뀔 때만 본다. 바꿀 것이 없으면 결제 서버의 가격 목록을 묻지 않는다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)
    round_ = await round_repository.find_latest_round(session, table_id)

    if is_unchanged(table, round_, data.narration_model):
        return table
    found = await require_pickable(session, picker, data.narration_model)

    table.narration_model = data.narration_model
    forget_retire_notices(table)
    applied = takes_new_model(round_)
    if applied:
        await apply_to_round(session, round_, data.narration_model, found)
    payload = {
        'narration_model': data.narration_model,
        'round': round_.number if applied else None,
        'price': price_payload(round_) if applied else None,
    }
    recorder.record(session, table, EventType.NARRATION_MODEL_CHANGED, actor_id=host_id, payload=payload)
    return await save(session, table)
