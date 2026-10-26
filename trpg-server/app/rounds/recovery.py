# trpg-server/app/rounds/recovery.py

"""
서술을 맡은 작업이 사라진 라운드를 찾아 다시 맡긴다(#275, #809). 서버의 시계가 몇 초마다 부른다(app/rounds/clock.py).

서술은 서버 프로세스 안의 작업이다(app/core/jobs.py). 서버가 서술 도중에 죽거나 꺼지면 작업이 사라지고,
라운드는 실패도 적히지 않은 채 닫는 중에 남는다. 작업의 자리가 다 차서 맡지 않았을 때도 같다.
전에는 방장이 닫기를 다시 눌러야 했다. 방장이 자리를 비웠으면 테이블이 거기서 멈췄다.

라운드는 DB 에 "닫는 중"으로 남아 있다. 이것이 사라지지 않는 대기 줄이다. 따로 큐를 두지 않고 이 줄을 다시 읽는다.
  - 사라졌다고 보는 것: 닫는 중이고, 실패를 적지 않았고, 닫기 시작한 지 service.CLOSING_RETRY_SECONDS 가 지났다.
    방장이 다시 맡길 수 있게 되는 때와 같다. 작업이 살아 있을 수 있는 가장 긴 시간보다 길어서,
    아직 도는 서술 위에 또 서술을 맡기지 않는다.
  - 실패를 적은 라운드는 다시 맡기지 않는다. 크레딧이 모자랐거나 모델이 끝내 실패한 것이다.
    그대로 다시 하면 같은 실패를 되풀이하며 값만 든다. 방장과 크레딧 기다리기(app/rounds/credit_waits.py)의 몫이다.
  - 다시 맡기는 것은 방장이 다시 맡길 때와 같다. 닫기 시작한 시각을 지금으로 고치고 서술을 맡긴다.
    이벤트를 다시 적지도, 주사위를 다시 굴리지도 않는다.
  - 스스로 다시 맡기는 것은 라운드마다 AUTO_RETRY_LIMIT 번까지다. 어떤 서술이 할 때마다 서버를 죽인다면
    끝없이 같은 사고를 되풀이하게 된다. 넘으면 서술을 그만둔다(stalled, service.abandon_narration).
    잡아 둔 서술 값은 돌려주고, 엔진이 정한 결과로 다음 라운드를 연다. 서술이 끝내 실패한 것과 같은 끝이다.
  - 사라진 것은 서술의 실패로 세지 않는다(narration_failures).
    서버가 죽은 일이 방장이 다시 맡길 수 있는 횟수를 쓰지 않게 한다.
    방장에게 넘기지도 않는다. 같은 서술이 또 서버를 죽일 수 있고, 방장이 자리를 비웠으면 테이블이 거기서 멈춘다.

찾을 때는 잠그지 않고, 하기 전에 테이블을 잠그고 다시 본다. 서버가 여럿이어도 한 서버만 다시 맡긴다.
먼저 잠근 서버가 닫기 시작한 시각을 고치면, 뒤의 서버는 고친 시각을 보고 그냥 지나간다.
서버가 뜰 때 시계의 첫 바퀴가 곧바로 돈다. 그래서 서버를 다시 띄운 뒤에 남은 라운드도 이 길로 찾는다.
"""

import enum
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.price_list import FREE_PRICES, PriceList
from app.rounds import repository, service
from app.rounds.models import Round, RoundStatus
from app.rounds.service import NarrationScheduler, hand_over, save
from app.tables import repository as table_repository
from app.tables.models import GameTable, TableStatus

logger = logging.getLogger(__name__)

# 서버가 스스로 다시 맡기는 횟수의 상한. 라운드마다 센다. 방장이 다시 맡기면 다시 센다
AUTO_RETRY_LIMIT = 2
# 스스로 다시 맡기기를 그만둘 때 이벤트(narration_abandoned)에 적는 이유
STALLED = 'stalled'
# 그만둔 줄의 오류 코드(docs/observability.md)
STALLED_ERROR_CODE = 'round.stalled'
# 로그의 operation. 서버의 시계가 한 바퀴 안에서 부른다
RECOVER_OPERATION = 'round.recover'


class Recovery(enum.StrEnum):
    """라운드 하나를 보고 한 일."""

    # 할 일이 없었다. 그사이에 닫혔거나, 방장이 다시 맡겼거나, 다른 서버가 먼저 했다
    NOTHING = 'nothing'
    # 서술을 다시 맡겼다
    RETRIED = 'retried'
    # 다시 맡기기를 그만두고 서술을 그만뒀다. 엔진의 결과로 다음 라운드를 열었다
    GAVE_UP = 'gave_up'


def vanished_before(now: datetime) -> datetime:
    """이 시각보다 먼저 닫기 시작했는데 아직 닫는 중이면 서술을 맡은 작업이 사라진 것으로 본다."""
    return now - timedelta(seconds=service.CLOSING_RETRY_SECONDS)


def is_vanished(round_: Round, now: datetime) -> bool:
    """서술을 맡은 작업이 사라졌는가. 닫는 중이고, 실패를 적지 않았고, 닫기 시작한 지 한참 지났다."""
    return (
        round_.status == RoundStatus.CLOSING
        and round_.narration_failed_at is None
        and round_.closing_at <= vanished_before(now)
    )


def can_retry(round_: Round) -> bool:
    """서버가 스스로 다시 맡길 수 있는가. 정해 둔 횟수를 다 쓰지 않았다."""
    return round_.auto_retries < AUTO_RETRY_LIMIT


def rearm(round_: Round, now: datetime) -> None:
    """서술을 다시 맡길 수 있게 고친다. 닫기 시작한 시각을 지금으로 고치고 스스로 맡긴 횟수를 하나 올린다."""
    round_.closing_at = now
    round_.auto_retries += 1


async def lock_vanished_round(
    session: AsyncSession, table_id: uuid.UUID, now: datetime
) -> tuple[GameTable, Round] | None:
    """
    테이블을 잠그고, 서술을 맡은 작업이 사라진 라운드를 찾는다.

    테이블이 없거나, 진행 중이 아니거나, 가장 최근 라운드가 그런 라운드가 아니면 None.
    """
    table = await table_repository.lock_table(session, table_id)
    if table is None or table.status != TableStatus.PLAYING:
        return None
    round_ = await repository.find_latest_round(session, table_id)
    if round_ is None or not is_vanished(round_, now):
        return None
    return table, round_


async def retry(
    session: AsyncSession, table: GameTable, round_: Round, now: datetime, scheduler: NarrationScheduler
) -> None:
    """서술을 다시 맡긴다. 저장한 뒤에 맡긴다. 작업이 견주는 닫기 시작한 시각이 DB 에 적힌 값과 같아야 한다."""
    rearm(round_, now)
    hand_over(scheduler, await save(session, table))
    logger.info(
        '서술을 맡은 작업이 사라져 다시 맡겼습니다',
        extra={
            'operation': RECOVER_OPERATION,
            'table_id': str(table.id),
            'round': round_.number,
            'auto_retries': round_.auto_retries,
        },
    )


async def give_up(session: AsyncSession, table: GameTable, round_: Round, prices: PriceList = FREE_PRICES) -> None:
    """
    다시 맡기기를 그만두고 서술을 그만둔다(stalled). 앉은 사람 모두에게 알린다. 저장한다.

    잠근 테이블의 라운드를 받는다(lock_vanished_round). 서술의 실패로 세지 않는다.
    값을 받지 않고(홀드를 돌려줄 것으로 적는다), 엔진의 결과로 다음 라운드를 연다(service.abandon_narration).
    사람이 봐야 하는 일이라 warning 으로 남긴다. 같은 서술이 되풀이해 사라졌다.
    """
    number, retries = round_.number, round_.auto_retries
    await service.abandon_narration(session, table, round_, STALLED, prices)
    logger.warning(
        '서술을 맡은 작업이 되풀이해 사라져 서술을 그만뒀습니다',
        extra={
            'operation': RECOVER_OPERATION,
            'table_id': str(table.id),
            'round': number,
            'auto_retries': retries,
            'error_code': STALLED_ERROR_CODE,
        },
    )


async def recover(
    session: AsyncSession,
    table_id: uuid.UUID,
    now: datetime,
    scheduler: NarrationScheduler,
    prices: PriceList = FREE_PRICES,
) -> Recovery:
    """
    테이블 하나의 사라진 서술을 다시 맡기거나 그만둔다. 무엇을 했는지 돌려준다.

    prices 는 그만둘 때 다음 라운드에 알릴 값을 찾는 가격 목록이다.
    """
    found = await lock_vanished_round(session, table_id, now)
    if found is None:
        # 잠금을 푼다. 바꾼 것이 없다. 되돌리기(rollback)는 세션이 들고 있던 객체를 낡은 것으로 만든다
        await session.commit()
        return Recovery.NOTHING
    table, round_ = found
    if not can_retry(round_):
        await give_up(session, table, round_, prices)
        return Recovery.GAVE_UP
    await retry(session, table, round_, now, scheduler)
    return Recovery.RETRIED
