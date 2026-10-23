# trpg-server/app/tables/model_retirement.py

"""
테이블의 서술 모델이 은퇴할 때 미리 알리고, 은퇴하면 같은 회사의 다른 모델로 바꾼다(유저 결정, 2026-10-18).

알리기
  - 은퇴일이 30, 14, 7, 1 일 남았을 때 한 번씩, 모두 네 번 알린다(narration_model_retiring). 앉은 사람 모두가 본다.
  - 서버가 꺼져 있다가 늦게 보면 지금 닿은 단계 하나만 알린다. 지나간 단계를 몰아서 알리지 않는다.
  - 어느 은퇴일의 몇 일 단계까지 알렸는지 테이블에 적는다(retire_notice_for, retire_notice_days).
    은퇴일이 미뤄지거나 모델이 바뀌면 처음부터 다시 센다.
  - 은퇴일이 정해진 것은 화면이 고를 수 있는 모델의 목록(GET /tables/narration-models 의 retires_on)으로도 안다.

바꾸기
  - 은퇴했을 때만 바꾼다. 운영자가 잠깐 끄거나 결제 서버가 판매를 멈춘 것은 바꾸지 않는다.
    다시 켜질 수 있다. 그때는 지금처럼 방장에게 알리고 방장이 바꾼다(app/billing/settling.py).
  - 대신 쓸 모델은 시나리오의 추천 모델과 같은 규칙이다(app/catalog/offers.py 의 replacement_for).
    운영자가 정한 회사의 대체 모델이 먼저, 없으면 같은 회사의 standard 중 가장 싼 모델이다.
  - 방장이 모델을 바꾸는 것과 같은 길로 바꾼다(app/tables/narration_models.py). 아직 서술하지 않은 지금 라운드도 바꾸고
    그 라운드의 청구를 새 가격표로 다시 건다. 바꾼 것은 이벤트로 남긴다(narration_model_replaced). 몰래 바꾸지 않는다.
  - 같은 회사에 대신할 모델이 없으면 바꾸지 않고 알린다(narration_model_unavailable). 그 은퇴일에 한 번이다.
    방장이 모델을 고르기 전까지 그 테이블은 서술할 수 없다.

알림함
  - 위의 세 이벤트는 방장의 알림함에도 간다(app/notifications/outbox.py 의 tell_host). 이벤트와 같은 트랜잭션에
    발송함에 적고, 알림 서버에는 뒤에서 보낸다. 모델을 바꿀 수 있는 사람이 방장이라 방장에게만 보낸다.

언제 보나
  - 뒤에서 도는 작업이 한 시간마다 은퇴일이 30 일 안에 든 모델의 테이블을 본다(app/tables/retirement_watch.py).
  - 라운드가 열린 뒤에도 그 테이블을 한 번 본다. 작업이 아직 돌지 않았어도 놓치지 않는다.

HTTP 를 모른다. 테이블을 잠그고 한다. 저장(commit)은 부른 쪽이 한다.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from ai_core.catalog_contract import is_retired
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.price_list import PriceList
from app.catalog import offers
from app.catalog import repository as catalog
from app.catalog.models import AiModel
from app.catalog.offers import OfferedModel
from app.catalog.steps import steps_of
from app.events import recorder
from app.events.models import EventType
from app.notifications import outbox
from app.rounds import repository as round_repository
from app.rounds.round_price import price_payload
from app.tables import repository as table_repository
from app.tables.models import GameTable, TableStatus
from app.tables.narration_models import apply_to_round, forget_retire_notices, takes_new_model

# 은퇴일 며칠 전에 알리는가. 큰 것부터다
NOTICE_DAYS = (30, 14, 7, 1)
# 대신할 모델이 없다고 알렸다는 표시. 알린 단계(retire_notice_days)에 이 값을 적는다
UNAVAILABLE_NOTICE = 0
# 바꾼 까닭. 지금은 은퇴뿐이다
RETIRED = 'retired'


@dataclass(frozen=True)
class Checked:
    """테이블 하나를 보고 한 일. 알렸나, 바꿨나, 대신할 모델이 없다고 알렸나."""

    noticed: bool = False
    replaced: bool = False
    stranded: bool = False

    def busy(self) -> bool:
        """한 일이 있었는가."""
        return self.noticed or self.replaced or self.stranded


NOTHING = Checked()


def days_left(retires_on: date, today: date) -> int:
    """은퇴일까지 남은 날. 은퇴일 당일은 0 이다(그날부터 은퇴다)."""
    return (retires_on - today).days


def notice_stage(retires_on: date, today: date) -> int | None:
    """
    지금 닿은 알림의 단계(30, 14, 7, 1 중 하나). 아직 30 일보다 멀거나 이미 은퇴했으면 None.

    20 일 남았으면 30, 5 일 남았으면 7, 하루 남았으면 1 이다.
    """
    left = days_left(retires_on, today)
    if left <= 0:
        return None
    reached = [days for days in NOTICE_DAYS if left <= days]
    return min(reached, default=None)


def already_noticed(table: GameTable, retires_on: date, stage: int) -> bool:
    """그 은퇴일의 그 단계(또는 더 가까운 단계)까지 이미 알렸는가."""
    if table.retire_notice_for != retires_on or table.retire_notice_days is None:
        return False
    return table.retire_notice_days <= stage


def mark_noticed(table: GameTable, retires_on: date, stage: int) -> None:
    """그 은퇴일의 그 단계까지 알렸다고 적는다."""
    table.retire_notice_for = retires_on
    table.retire_notice_days = stage


def is_watched(table: GameTable) -> bool:
    """볼 테이블인가. 끝나지 않았고 서술 모델이 있다."""
    return table.status != TableStatus.ENDED and table.narration_model is not None


async def replacement_of(
    session: AsyncSession, prices: PriceList, table: GameTable, model: AiModel, now: datetime
) -> OfferedModel | None:
    """
    은퇴하는 모델 대신 쓸 같은 회사의 모델. 테이블의 단계(#387)를 파는 모델만 된다. 없으면 None.

    단계를 바꿔 가며 대신하지 않는다. 단계까지 바뀌면 앉은 사람이 동의한 값과 너무 멀어진다. 그때는 방장이 고른다.
    가격 목록을 받지 못했고 받아 둔 것도 없으면 PriceListUnavailable 이 그대로 올라간다. 다음에 다시 본다.
    """
    return await offers.find_replacement(
        session, prices, model.vendor, now, excluding=model.slug, steps=steps_of(table)
    )


def notify_retiring(session: AsyncSession, table: GameTable, model: AiModel, stage: int, today: date) -> None:
    """은퇴가 다가온다고 알리고(방장의 알림함에도) 그 단계를 적는다."""
    payload = {
        'narration_model': model.slug,
        'retires_on': model.retires_on.isoformat(),
        'days_left': days_left(model.retires_on, today),
    }
    event = recorder.record(session, table, EventType.NARRATION_MODEL_RETIRING, payload=payload)
    outbox.tell_host(session, table, event)
    mark_noticed(table, model.retires_on, stage)


async def replace_model(session: AsyncSession, table: GameTable, retired: str, replacement: OfferedModel) -> None:
    """
    테이블의 모델을 대신 쓸 모델로 바꾸고 알린다. 아직 서술하지 않은 지금 라운드도 바꾸고 새 가격표로 다시 건다.

    방장이 바꾸는 것(app/tables/narration_models.py)과 같은 규칙이다. 다른 것은 바꾼 사람이 서버라는 것뿐이다.
    """
    round_ = await round_repository.find_latest_round(session, table.id)
    table.narration_model = replacement.slug
    applied = takes_new_model(round_)
    if applied:
        await apply_to_round(session, round_, replacement.slug, steps_of(table), replacement)
    forget_retire_notices(table)
    payload = {
        'from': retired,
        'narration_model': replacement.slug,
        'reason': RETIRED,
        'round': round_.number if applied else None,
        'price': price_payload(round_) if applied else None,
    }
    event = recorder.record(session, table, EventType.NARRATION_MODEL_REPLACED, payload=payload)
    outbox.tell_host(session, table, event)


def notify_stranded(session: AsyncSession, table: GameTable, model: AiModel) -> None:
    """은퇴한 모델 대신 쓸 모델이 같은 회사에 없다고 알린다. 그 은퇴일에 한 번이다."""
    payload = {'narration_model': model.slug, 'reason': RETIRED}
    event = recorder.record(session, table, EventType.NARRATION_MODEL_UNAVAILABLE, payload=payload)
    outbox.tell_host(session, table, event)
    mark_noticed(table, model.retires_on, UNAVAILABLE_NOTICE)


async def handle_retired(
    session: AsyncSession, table: GameTable, model: AiModel, prices: PriceList, now: datetime
) -> Checked:
    """은퇴한 모델을 쓰는 테이블. 대신 쓸 모델이 있으면 바꾸고, 없으면 (아직 알리지 않았으면) 알린다."""
    replacement = await replacement_of(session, prices, table, model, now)
    if replacement is not None:
        await replace_model(session, table, model.slug, replacement)
        return Checked(replaced=True)
    if already_noticed(table, model.retires_on, UNAVAILABLE_NOTICE):
        return NOTHING
    notify_stranded(session, table, model)
    return Checked(stranded=True)


def handle_retiring(session: AsyncSession, table: GameTable, model: AiModel, today: date) -> Checked:
    """은퇴가 다가오는 모델을 쓰는 테이블. 새 단계에 닿았으면 알린다."""
    stage = notice_stage(model.retires_on, today)
    if stage is None or already_noticed(table, model.retires_on, stage):
        return NOTHING
    notify_retiring(session, table, model, stage, today)
    return Checked(noticed=True)


async def check_table(session: AsyncSession, table: GameTable, prices: PriceList, now: datetime) -> Checked:
    """
    잠근 테이블 하나를 본다. 모델이 은퇴했으면 바꾸고, 은퇴가 다가오면 알린다. 저장하지 않는다.

    끝난 테이블, 모델이 없는 옛 테이블, 은퇴일이 없는 모델은 볼 것이 없다.
    """
    if not is_watched(table):
        return NOTHING
    model = await catalog.get_model(session, table.narration_model)
    if model is None or model.retires_on is None:
        return NOTHING
    if is_retired(model, now.date()):
        return await handle_retired(session, table, model, prices, now)
    return handle_retiring(session, table, model, now.date())


async def watched_table_ids(session: AsyncSession, today: date) -> list[uuid.UUID]:
    """은퇴일이 30 일 안에 들었거나 이미 지난 모델을 쓰는, 끝나지 않은 테이블들."""
    return await table_repository.find_tables_near_retirement(session, today, max(NOTICE_DAYS))
