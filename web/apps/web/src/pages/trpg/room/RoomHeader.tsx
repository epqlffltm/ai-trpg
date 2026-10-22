// web/apps/web/src/pages/trpg/room/RoomHeader.tsx
// 테이블 방의 머리. 제목, 상태, 시나리오(소개로), 스트림의 상태, 나가기.

import { Link } from 'react-router';
import type { TableDetail } from '../../../api/types';
import { tableStatusLabel } from '../../home/labels';
import { LeaveButton } from './LeaveButton';
import type { StreamStatus } from './useTableStream';

export function RoomHeader({ table, stream }: { table: TableDetail; stream: StreamStatus }) {
  return (
    <header className="page-head room__head">
      <div>
        <h1>{table.title}</h1>
        <p className="hint">
          {tableStatusLabel(table.status)} · {table.member_count}/{table.capacity}명 ·{' '}
          <Link to={`/trpg/scenarios/${table.scenario_id}`}>시나리오 소개</Link>
        </p>
      </div>
      <div className="room__head-actions">
        <StreamBadge stream={stream} />
        {table.status === 'ended' ? null : <LeaveButton tableId={table.id} />}
      </div>
    </header>
  );
}

/** 실시간으로 받고 있는지. 끊겨 다시 붙는 중이면 알린다(그동안의 것은 다시 붙으면 온다) */
function StreamBadge({ stream }: { stream: StreamStatus }) {
  const label = streamLabel(stream);
  if (!label) return null;
  return (
    <span className="stream-badge" role="status">
      {label}
    </span>
  );
}

export function streamLabel(stream: StreamStatus): string | null {
  switch (stream.state) {
    case 'connecting':
      return '연결하는 중';
    case 'open':
      return null;
    case 'reconnecting':
      return `연결이 끊겨 ${Math.ceil(stream.inMs / 1000)}초 뒤에 다시 붙습니다`;
    case 'stopped':
      return stream.reason === 'table_ended' ? null : '실시간 연결이 끝났습니다';
  }
}
