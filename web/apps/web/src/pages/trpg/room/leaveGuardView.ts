// web/apps/web/src/pages/trpg/room/leaveGuardView.ts
// 떠나기 전의 물음(LeaveGuard, #1344)이 물을지 정하는 순수한 함수.
// 진행 중인 테이블 방에서 다른 곳으로 가면 묻는다. 같은 테이블 안에서 옮기는 것과, 나가기 단추로 이미 나간 뒤 로비로
// 가는 것(LEFT_TABLE)은 묻지 않는다.

import type { Location } from 'react-router';

/** 이미 나갔다는 표시. 나가기 단추가 로비로 갈 때 이동의 state 로 싣는다 */
export const LEFT_TABLE = { leftTable: true } as const;

function hasLeft(state: unknown): boolean {
  return typeof state === 'object' && state !== null && (state as { leftTable?: unknown }).leftTable === true;
}

/** 이 이동 앞에서 물을까 */
export function shouldAsk(tableId: string, current: Location, next: Location): boolean {
  if (hasLeft(next.state)) return false;
  const room = `/trpg/tables/${tableId}`;
  const staying = next.pathname === room || next.pathname.startsWith(`${room}/`);
  return current.pathname !== next.pathname && !staying;
}
