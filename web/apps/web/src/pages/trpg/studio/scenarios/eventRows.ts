// web/apps/web/src/pages/trpg/studio/scenarios/eventRows.ts
// 퀘스트와 사건 규칙의 목록의 줄들(B9 퀘스트·사건 탭). 순수한 함수다.
// 붙인 로어북의 사건 항목 모두와, 규칙이 가리키지만 붙인 로어북에 없는 사건(로어북을 뗐거나 항목을 지웠다).

import type { EntryChoice } from './useLoreEntries';

export type EventRow = { id: string; name: string; listed: boolean };

export function eventRows(events: EntryChoice[], ruleIds: string[]): EventRow[] {
  const listed = events.map((event) => ({ id: event.id, name: event.name, listed: true }));
  const orphans = ruleIds.filter((id) => !events.some((event) => event.id === id)).map((id) => ({ id, name: '(붙인 로어북에 없는 사건)', listed: false }));
  return [...listed, ...orphans];
}
