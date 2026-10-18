// board-server/src/notifications/outbox.ts

/**
 * 발송함에 알림을 적는다. 부른 쪽의 트랜잭션(manager) 안에서 적는다. 그 일과 함께 저장되거나 함께 되돌려진다.
 */

import { EntityManager } from 'typeorm';
import { NewNotice } from './notices.js';
import { OutgoingNotification } from './outgoing-notification.entity.js';

/** 알림들을 발송함에 적는다. 없으면 아무것도 하지 않는다. 바로 보낼 차례다(next_attempt_at 이 비어 있다). */
export async function queueNotices(
  manager: EntityManager,
  notices: NewNotice[],
): Promise<void> {
  if (notices.length === 0) {
    return;
  }
  await manager.save(
    OutgoingNotification,
    notices.map((notice) => ({
      userId: notice.userId,
      kind: notice.kind,
      sourceKey: notice.sourceKey,
      payload: notice.payload,
    })),
  );
}
