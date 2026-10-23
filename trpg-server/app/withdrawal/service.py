# trpg-server/app/withdrawal/service.py

"""
탈퇴한 사람을 게임에서 정리한다(docs/architecture/withdrawal.md 의 "마칠 때: 다른 서버", 2026-10-21 유저 결정).

  - 보관함(trpg 페르소나)을 지운다. 가져간 테이블은 사본으로 돈다
  - 시나리오의 공개를 모두 내린다. 자산(시나리오, 세계관, 룰북, 로어북, 도감)과 판은 지우지 않고 그대로 둔다.
    진행 중인 테이블은 판의 사본으로 계속 돈다. 공개를 내렸으니 로비에서 새로 고를 수는 없다
  - 아직 보내지 않은 그 사람의 알림을 지운다
  - 모집 중이거나 진행 중인 테이블에서 나간다. 스스로 나가기와 같다(방장이면 넘기고, 마지막이면 끝낸다).
    끝난 테이블의 자리는 기록으로 남긴다
  - 테이블의 기록(채팅, 선언, 쪽지)은 함께한 사람의 기록이라 남긴다. 이름은 인증 서버가 null 로 준다("탈퇴한 사용자")

앞의 셋은 한 트랜잭션이다. 테이블은 하나씩 잠그고 나간다. 테이블마다 따로 저장하므로 도중에 실패하면
일부만 나간 채로 남는다. 그래도 된다. 인증 서버가 다시 보내고, 다시 하면 남은 것만 한다(멱등).
테이블을 한꺼번에 잠그지 않는다. 여러 테이블을 한 트랜잭션에서 잠그면 다른 요청과 서로 기다리다 막힐 수 있다.
"""

import uuid

from server_core.notifications import repository as notifications
from sqlalchemy.ext.asyncio import AsyncSession

from app.listings import repository as listings
from app.notifications.models import OutgoingNotification
from app.personas import repository as personas
from app.tables import repository as tables
from app.tables import service as seating


async def erase_belongings(session: AsyncSession, user_id: uuid.UUID) -> None:
    """보관함을 지우고, 공개를 내리고, 보내지 않은 알림을 지운다. 한 번에 저장한다."""
    await personas.delete_all_owned(session, user_id)
    await listings.unpublish_all_owned(session, user_id)
    await notifications.drop_for_user(session, OutgoingNotification, user_id)
    await session.commit()


async def leave_tables(session: AsyncSession, user_id: uuid.UUID) -> None:
    """끝나지 않은 테이블에서 하나씩 나간다."""
    for table_id in await tables.list_unfinished_seated_ids(session, user_id):
        await seating.leave_for_withdrawal(session, user_id, table_id)


async def process_withdrawal(session: AsyncSession, user_id: uuid.UUID) -> None:
    """탈퇴한 사람을 정리한다."""
    await erase_belongings(session, user_id)
    await leave_tables(session, user_id)
