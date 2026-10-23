# trpg-server/app/tables/narration_models.py

"""
테이블의 서술 모델과 단계(#387)를 바꾼다. 방장만 한다. 모델과 단계는 함께 한 가격표를 고르는 것이라 함께 바꾼다.

시작하면 고정이다(유저 결정, 2026-10-19). 서술 값은 앉은 사람 모두가 낸다. 들어오는 사람은 모델과 값을 보고 앉으므로
앉는 것이 그 모델에 대한 동의다. 시작한 뒤에 방장 혼자 비싼 모델로 바꾸면 남의 값을 정하게 된다.
  - 모집 중에는 바꿀 수 있다.
  - 시작한 뒤에는 지금 쓰는 모델을 쓸 수 없을 때만 바꿀 수 있다. 운영자가 껐거나, 결제 서버가 팔지 않거나,
    은퇴했는데 같은 회사에 대신할 모델이 없다(app/tables/model_retirement.py). 그때 방장이 다시 고른다(유저 결정).
    지금 쓰는 모델은 테이블의 모델과, 서술이 실패해 멈춘 라운드의 모델이다(models_in_use).
    모두 쓸 수 있으면 409(narration_model_locked)다.
  - 은퇴해 대신할 모델이 있으면 엔진이 바꾼다(app/tables/model_retirement.py). 방장이 바꾸는 길과 같은 함수를 쓴다.

모델은 라운드를 열 때 그 라운드의 것으로 굳는다(app/rounds/opener.py). 바꾼 값은 다음 라운드부터 쓴다.
다만 지금 라운드가 아직 서술되지 않았고 서술이 돌고 있지도 않으면 그 라운드의 모델도 함께 바꾼다.
  - 선언을 받는 중인 라운드
  - 서술이 실패해 멈춘 라운드(닫는 중, 실패를 적었다)
판매를 멈춘 모델 때문에 막힌 라운드를 방장이 풀 수 있게 하려는 것이다.
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
from app.catalog import offers
from app.catalog.offers import OfferedModel
from app.catalog.steps import NarrationSteps, steps_of
from app.events import recorder
from app.events.models import EventType
from app.rounds import repository as round_repository
from app.rounds.models import Round, RoundStatus
from app.rounds.round_price import announce, price_payload
from app.tables.errors import Conflict, TableConflictError
from app.tables.model_picker import ModelPicker, require_pickable
from app.tables.models import GameTable, TableStatus
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


# 지금 쓰는 것 하나. 서술 모델(없으면 옛 것)과 단계다. 둘이 한 가격표다
Choice = tuple[str | None, NarrationSteps]


def choice_of(row: GameTable | Round) -> Choice:
    """테이블이나 라운드의 모델과 단계."""
    return row.narration_model, steps_of(row)


def is_unchanged(table: GameTable, round_: Round | None, chosen: Choice) -> bool:
    """
    바꿀 것이 없는가. 테이블의 모델과 단계가 같고, 지금 바꿀 수 있는 라운드가 있으면 그 라운드의 것도 같다.
    """
    if choice_of(table) != chosen:
        return False
    return not takes_new_model(round_) or choice_of(round_) == chosen


def forget_retire_notices(table: GameTable) -> None:
    """은퇴를 알린 것을 지운다. 모델이 바뀌면 새 모델의 은퇴일로 처음부터 다시 센다(app/tables/model_retirement.py)."""
    table.retire_notice_for = None
    table.retire_notice_days = None


def choices_in_use(table: GameTable, round_: Round | None) -> list[Choice]:
    """
    지금 쓰는 모델과 단계들. 테이블의 것과, 지금 바꿀 수 있는 라운드(takes_new_model)가 있으면 그 라운드의 것이다.

    서술이 실패해 멈춘 라운드는 연 때의 모델과 단계로 다시 서술한다. 테이블의 것을 쓸 수 있어도 그 라운드의 것을 못 쓰면
    라운드가 풀리지 않는다.
    """
    if takes_new_model(round_) and choice_of(round_) != choice_of(table):
        return [choice_of(table), choice_of(round_)]
    return [choice_of(table)]


async def is_usable(session: AsyncSession, picker: ModelPicker, chosen: Choice) -> bool:
    """
    그 모델과 단계를 지금 쓸 수 있는가. 그 단계로 고를 수 있는 목록에 있으면 쓸 수 있다(app/catalog/offers.py).

    모델이 없는 옛 테이블과 옛 라운드는 쓸 수 없는 것으로 본다. 방장이 모델을 고르게 둔다.
    그 단계의 가격표를 팔지 않게 됐어도 쓸 수 없다. 방장이 다른 단계나 모델을 고른다.
    가격 목록을 받지 못했고 받아 둔 것도 없으면 PriceListUnavailable 이 그대로 올라간다(503).
    """
    model, steps = chosen
    if model is None:
        return False
    return await offers.find_offered(session, picker.prices, model, picker.now, steps) is not None


async def require_changeable(
    session: AsyncSession, picker: ModelPicker, table: GameTable, round_: Round | None
) -> None:
    """
    지금 서술 모델을 바꿀 수 있는지 확인한다. 아니면 TableConflictError(narration_model_locked).

    모집 중이면 늘 된다. 시작한 뒤에는 지금 쓰는 모델과 단계(choices_in_use) 중 하나라도 쓸 수 없을 때만 된다.
    단계만 바꾸는 것도 같다. 앉은 사람 모두가 그 값을 보고 앉았다.
    """
    if table.status == TableStatus.RECRUITING:
        return
    for chosen in choices_in_use(table, round_):
        if not await is_usable(session, picker, chosen):
            return
    raise TableConflictError(Conflict.NARRATION_MODEL_LOCKED)


async def apply_to_round(
    session: AsyncSession, round_: Round, model: str, steps: NarrationSteps, price: OfferedModel | None
) -> None:
    """
    라운드의 모델과 단계를 바꾸고, 그 라운드의 청구를 새 가격표로 다시 걸게 적는다.

    price 는 새 모델과 단계의 지금 값이다. 라운드에 알린 값도 바꾼다(app/rounds/round_price.py).
    """
    round_.narration_model = model
    round_.input_step, round_.output_step = steps.input, steps.output
    announce(round_, price)
    await charges.reprice_round(session, round_, datetime.now(UTC))


async def change_narration_model(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, data: NarrationModelUpdate, picker: ModelPicker
) -> GameTable:
    """
    방장이 서술 모델과 단계를 바꾼다. 지금 라운드가 바꿀 수 있는 라운드면(takes_new_model) 그 라운드에도 적용한다.

    방장이 아니면 NotHostError, 끝난 테이블이면 TableConflictError,
    고를 수 없는 모델이면 TableOptionError(narration_model),
    그 모델이 팔지 않는 단계면 TableOptionError(narration_steps).
    시작한 테이블의 지금 쓰는 모델과 단계를 모두 쓸 수 있으면 TableConflictError(narration_model_locked).
    바꿀 것이 없으면 아무것도 적지 않는다. 바뀐 것이 없는데 이벤트가 쌓이지 않게 한다.
    고를 수 있는지는 잠근 뒤, 값이 바뀔 때만 본다. 바꿀 것이 없으면 결제 서버의 가격 목록을 묻지 않는다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)
    round_ = await round_repository.find_latest_round(session, table_id)
    steps = NarrationSteps(data.input_step, data.output_step)

    if is_unchanged(table, round_, (data.narration_model, steps)):
        return table
    await require_changeable(session, picker, table, round_)
    found = await require_pickable(session, picker, data.narration_model, steps)

    if table.narration_model != data.narration_model:
        forget_retire_notices(table)
    table.narration_model = data.narration_model
    table.input_step, table.output_step = steps.input, steps.output
    applied = takes_new_model(round_)
    if applied:
        await apply_to_round(session, round_, data.narration_model, steps, found)
    payload = {
        'narration_model': data.narration_model,
        'input_step': steps.input,
        'output_step': steps.output,
        'round': round_.number if applied else None,
        'price': price_payload(round_) if applied else None,
    }
    recorder.record(session, table, EventType.NARRATION_MODEL_CHANGED, actor_id=host_id, payload=payload)
    return await save(session, table)
