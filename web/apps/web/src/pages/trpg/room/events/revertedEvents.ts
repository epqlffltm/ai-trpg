// web/apps/web/src/pages/trpg/room/events/revertedEvents.ts
// 방장이 되돌린 라운드(#288)의 이벤트를 뺀다. 순수한 함수다.
// 서버는 이벤트를 지우지 않고 round_reverted 를 덧붙인다. 그 payload 의 group 이 되돌린 닫힘의 묶음(action_group_id)이다.
// 닫힘, 판정, 바뀐 HP, 서술, 다음 라운드의 열림이 그 묶음에 든다. 없었던 일이라 일어난 일과 지난 이야기에서 뺀다.
// round_reverted 자체는 남긴다("방장이 되돌렸다"는 한 줄).

import type { TableEvent } from '../../../../api/types';

/** 되돌린 묶음들 */
export function revertedGroups(events: TableEvent[]): Set<string> {
  const groups = new Set<string>();
  for (const event of events) {
    const group = event.type === 'round_reverted' ? (event.payload ?? {}).group : undefined;
    if (typeof group === 'string') groups.add(group);
  }
  return groups;
}

/** 되돌린 묶음의 이벤트를 뺀 것. 차례는 그대로다 */
export function withoutReverted(events: TableEvent[]): TableEvent[] {
  const groups = revertedGroups(events);
  if (groups.size === 0) return events;
  return events.filter((event) => !groups.has(event.action_group_id));
}
