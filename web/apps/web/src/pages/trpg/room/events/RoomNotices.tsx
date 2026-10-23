// web/apps/web/src/pages/trpg/room/events/RoomNotices.tsx
// 지금 라운드 위의 알림. 서술을 막는 일(크레딧이 모자람, 모델을 쓸 수 없음 …)을 고른다(roomNotices.ts).
// 무엇을 할지는 글에 적는다. 단추는 방장의 운영(host/)에 있다. 여기서는 상태를 바꾸지 않는다.

import { Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import type { TableDetail } from '../../../../api/types';
import { eventsQuery } from '../roomQueries';
import { roomNotices } from './roomNotices';
import { useEventContext } from './useEventContext';

type Props = { table: TableDetail; currentRound: number | null; nameOfMember: (userId: string) => string };

export function RoomNotices({ table, currentRound, nameOfMember }: Props) {
  const events = useQuery(eventsQuery(table.id));
  const ctx = useEventContext(table, nameOfMember);
  if (table.status !== 'playing' || !events.data) return null;
  const notices = roomNotices(events.data.items, currentRound, ctx);
  if (notices.length === 0) return null;
  return (
    <div className="room-notices">
      {notices.map((notice) => (
        <Notice key={notice.key} tone={notice.tone}>
          {notice.text}
        </Notice>
      ))}
    </div>
  );
}
