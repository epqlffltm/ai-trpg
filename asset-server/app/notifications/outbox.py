# asset-server/app/notifications/outbox.py

"""
무엇을 누구에게 알리는가(#678). 발송함에 적기만 하고 저장(commit)은 부른 쪽이 그 조치와 함께 한다.

| 종류 | 언제, 누구에게 | 내용 |
| --- | --- | --- |
| character.hidden | 운영자가 숨겼다(직접, 또는 신고를 받아들여서). 캐릭터의 주인에게 | character_id, name |
| character.unhidden | 운영자가 숨김을 풀었다. 캐릭터의 주인에게 | character_id, name |
| character_report.handled | 운영자가 신고를 처리했다. 신고한 사람에게 | name |

  - 숨김이 바뀐 때만 주인에게 알린다. 이미 숨긴 캐릭터를 또 숨겨도 알림은 없다
  - 신고를 처리한 알림에는 결과(숨김, 기각)를 싣지 않는다. 신고한 사람이 결과로 상대를 짐작하거나
    운영 판단을 두고 다투지 않게 한다(docs/architecture/operators.md)
  - 사유는 싣지 않는다. 운영자가 쓴 자유 글이고, 감사 기록에만 남는다

열쇠(source_key)는 알림 서버가 같은 알림을 알아보는 것이다.
숨김과 풀기는 "<kind>:<캐릭터>:<감사 기록의 번호>" 라 조치마다 다르다.
신고의 처리는 "character_report.handled:<신고>" 다. 한 사람은 한 캐릭터를 한 번만 신고하므로 신고마다 한 번이다.
"""

import uuid

from server_core.notifications import repository
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.models import Character
from app.notifications.models import OutgoingNotification

# 알림 서버에 넣는 이 서버의 이름. 알림 서버의 주소와 비밀(ASSET_SERVER_SECRET)이 이 이름으로 정해진다
SOURCE = 'asset'

HIDDEN = 'character.hidden'
UNHIDDEN = 'character.unhidden'
REPORT_HANDLED = 'character_report.handled'


def put(session: AsyncSession, user_id: uuid.UUID, kind: str, source_key: str, payload: dict) -> OutgoingNotification:
    """발송함에 알림 하나를 적는다. 저장하지 않는다."""
    return repository.put(session, OutgoingNotification, user_id, kind, source_key, payload)


def hidden_kind(hidden: bool) -> str:
    """숨김과 풀기의 알림 종류."""
    return HIDDEN if hidden else UNHIDDEN


def tell_owner(session: AsyncSession, character: Character, hidden: bool, action_id: int) -> OutgoingNotification:
    """숨김이 바뀐 것을 주인에게 알린다. action_id 는 그 조치의 감사 기록 번호다."""
    kind = hidden_kind(hidden)
    payload = {'character_id': str(character.id), 'name': character.name}
    return put(session, character.owner_id, kind, f'{kind}:{character.id}:{action_id}', payload)


def tell_reporter(
    session: AsyncSession, character: Character, report_id: uuid.UUID, reporter_id: uuid.UUID
) -> OutgoingNotification:
    """신고 하나를 처리했다는 것을 신고한 사람에게 알린다. 결과는 싣지 않는다."""
    return put(session, reporter_id, REPORT_HANDLED, f'{REPORT_HANDLED}:{report_id}', {'name': character.name})


async def drop_for_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """그 사람에게 아직 보내지 않은 알림을 지운다(탈퇴). 저장하지 않는다."""
    await repository.drop_for_user(session, OutgoingNotification, user_id)
