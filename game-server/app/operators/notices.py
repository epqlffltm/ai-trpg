# game-server/app/operators/notices.py

"""
운영자의 제재를 당사자의 알림함에 알린다(#385, #392). 발송함에 적기만 한다(app/notifications/outbox.py).

제재(app/operators/sanctions.py)와 같은 트랜잭션에서 부른다. 제재가 되지 않았으면 알림도 없다.
알림 서버에는 뒤에서 보낸다. 알림 서버가 죽어 있어도 제재는 된다.

| 제재 | 받는 사람 | `kind` | `payload` |
| --- | --- | --- | --- |
| 시나리오 제재 | 제작자 | `scenario.sanctioned` | `scenario_id`, `title`, `version_number`, `publishing_banned` |
| 공개 금지(운영자가, 저절로) | 그 사람 | `publishing.banned` | `automatic` |
| 공개 금지 풀기 | 그 사람 | `publishing.unbanned` | 없음 |

사유(reason)는 싣지 않는다. 운영자가 감사 기록에 남기는 글(신고 번호, 짧은 메모)이라 신고한 사람이 드러날 수 있다.
운영자가 누구인지도 싣지 않는다. 테이블 끝내기의 이벤트와 같은 규칙이다(docs/architecture/operators.md).

열쇠(source_key)는 "<kind>:<감사 기록의 번호>" 다. 제재 하나에 감사 기록이 하나라서, 같은 사람이 여러 번 금지되고
풀려도 알림이 서로 다르다. 저절로 오른 공개 금지는 감사 기록이 따로 없어 원인인 시나리오 제재의 번호를 쓴다
(kind 가 달라 그 제재의 알림과 겹치지 않는다). 감사 기록의 번호가 있어야 하므로 기록을 flush 한 뒤에 부른다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications import outbox
from app.notifications.models import OutgoingNotification
from app.operators.models import OperatorAction

SCENARIO_SANCTIONED = 'scenario.sanctioned'
PUBLISHING_BANNED = 'publishing.banned'
PUBLISHING_UNBANNED = 'publishing.unbanned'


def action_key(kind: str, action: OperatorAction) -> str:
    """감사 기록에서 온 알림의 열쇠. 기록이 flush 되어 번호가 있어야 한다."""
    if action.id is None:
        raise ValueError('감사 기록을 flush 한 뒤에 알린다')
    return f'{kind}:{action.id}'


def tell_sanctioned(
    session: AsyncSession,
    action: OperatorAction,
    owner_id: uuid.UUID,
    title: str,
    version_number: int,
    publishing_banned: bool,
) -> OutgoingNotification:
    """시나리오가 제재되었다고 제작자에게 알린다. 그 판은 다시 공개하지 못하고, 고쳐서 새 판을 내면 공개할 수 있다."""
    payload = {
        'scenario_id': str(action.target_id),
        'title': title,
        'version_number': version_number,
        'publishing_banned': publishing_banned,
    }
    return outbox.put(session, owner_id, SCENARIO_SANCTIONED, action_key(SCENARIO_SANCTIONED, action), payload)


def tell_banned(
    session: AsyncSession, action: OperatorAction, user_id: uuid.UUID, automatic: bool
) -> OutgoingNotification:
    """공개가 금지되었다고 그 사람에게 알린다. automatic 이면 제재가 정해진 수에 닿아 저절로 오른 것이다."""
    payload = {'automatic': automatic}
    return outbox.put(session, user_id, PUBLISHING_BANNED, action_key(PUBLISHING_BANNED, action), payload)


def tell_unbanned(session: AsyncSession, action: OperatorAction, user_id: uuid.UUID) -> OutgoingNotification:
    """공개 금지가 풀렸다고 그 사람에게 알린다."""
    return outbox.put(session, user_id, PUBLISHING_UNBANNED, action_key(PUBLISHING_UNBANNED, action), {})
