// web/apps/web/src/pages/trpg/room/events/RoomNotices.tsx
// 지금 라운드 위의 알림. 서술을 막는 일(크레딧이 모자람, 모델을 쓸 수 없음 …)을 고른다(roomNotices.ts).
// 무엇을 할지는 글에 적는다. 단추는 방장의 운영(host/)에 있다. 여기서는 상태를 바꾸지 않는다.
// 내 크레딧이 모자라면 충전(A7)으로 가는 길을 붙인다. 기다리는 시간 안에 충전하면 게임 서버가 값을 다시 걸어 본다
// (trpg-server/app/billing/settler.py).

import { Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { TableDetail } from '../../../../api/types';
import { eventsQuery } from '../roomQueries';
import { roomNotices } from './roomNotices';
import { useEventContext } from './useEventContext';

type Props = { table: TableDetail; currentRound: number | null; myId: string | undefined; nameOfMember: (userId: string) => string };

export function RoomNotices({ table, currentRound, myId, nameOfMember }: Props) {
  const events = useQuery(eventsQuery(table.id));
  const ctx = useEventContext(table, nameOfMember);
  if (table.status !== 'playing' || !events.data) return null;
  const notices = roomNotices(events.data.items, currentRound, ctx, myId);
  if (notices.length === 0) return null;
  return (
    <div className="room-notices">
      {notices.map((notice) => (
        <Notice key={notice.key} tone={notice.tone}>
          {notice.text}
          {notice.charge ? (
            <>
              {' '}
              <Link to="/wallet/charge">충전하기</Link>
            </>
          ) : null}
        </Notice>
      ))}
    </div>
  );
}
