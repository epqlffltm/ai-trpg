# story-server/app/notifications/outbox.py

"""
무엇을 누구에게 알리는가(chat 과 같다). 발송함에 적기만 하고 저장(commit)은 부른 쪽이 그 처리와 함께 한다.

| 종류 | 언제, 누구에게 | 내용 |
| --- | --- | --- |
| story_report.handled | 운영자가 세션 속 답의 신고를 처리했다. 신고한 사람에게 | name(신고한 때의 세계관 이름) |

  - 결과(받아들임, 기각)를 싣지 않는다. asset 과 chat 의 신고와 같다(docs/architecture/operators.md)
  - 사유와 세션의 글은 싣지 않는다. 사유는 운영자가 쓴 자유 글이고 감사 기록에만 남는다
  - 알림 서버는 kind 마다 넣을 수 있는 서버를 정해 둔다. chat 의 message_report.handled 는 story 가 넣지 못한다

열쇠(source_key)는 "story_report.handled:<신고>" 다. 신고는 한 번만 처리하므로 신고마다 한 번이다.
"""

import uuid

from server_core.notifications import repository
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import OutgoingNotification
from app.reports.repository import HandledReport

# 알림 서버에 넣는 이 서버의 이름. 알림 서버의 주소와 비밀(STORY_SERVER_SECRET)이 이 이름으로 정해진다
SOURCE = 'story'

REPORT_HANDLED = 'story_report.handled'


def put(session: AsyncSession, user_id: uuid.UUID, kind: str, source_key: str, payload: dict) -> OutgoingNotification:
    """발송함에 알림 하나를 적는다. 저장하지 않는다."""
    return repository.put(session, OutgoingNotification, user_id, kind, source_key, payload)


def tell_reporter(session: AsyncSession, handled: HandledReport) -> OutgoingNotification:
    """신고를 처리했다는 것을 신고한 사람에게 알린다. 결과는 싣지 않는다."""
    key = f'{REPORT_HANDLED}:{handled.report_id}'
    return put(session, handled.reporter_id, REPORT_HANDLED, key, {'name': handled.world_name})


async def drop_for_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """그 사람에게 아직 보내지 않은 알림을 지운다(탈퇴). 저장하지 않는다."""
    await repository.drop_for_user(session, OutgoingNotification, user_id)
