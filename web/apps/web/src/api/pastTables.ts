// web/apps/web/src/api/pastTables.ts
// 내가 떠난 테이블(게임 서버, #428, B10). 시작한 테이블에서 나갔거나 내보내졌거나 크레딧이 모자라 빠진 사람이 떠난 때까지의 이야기를 읽는다.
// 앉은 사람의 길(테이블, 라운드)은 떠난 사람에게 404 다. 그래서 이벤트로만 읽는다(서술 gm_narration, 선언 player_action).
// 응답의 last_sequence 는 테이블의 마지막이 아니라 떠났다는 이벤트의 번호다. 떠난 적 없는 테이블은 404.

import { apiRequest } from './http';
import type { EventPage, PastTablePage } from './types';

const PAST = '/api/v1/game/tables/past';

/** 한 번에 읽는 이벤트 수(서버의 최대) */
export const PAST_EVENT_PAGE = 100;
/** 한 쪽에 읽는 떠난 테이블 수 */
export const PAST_TABLE_PAGE = 20;

/** 떠난 테이블. 최근에 떠난 것부터 */
export function fetchPastTables(offset: number, signal?: AbortSignal): Promise<PastTablePage> {
  return apiRequest<PastTablePage>(PAST, { query: { limit: PAST_TABLE_PAGE, offset }, ...(signal ? { signal } : {}) });
}

/** after 번 뒤의 이벤트(일어난 차례대로). 떠난 때까지만 */
export function fetchPastEvents(tableId: string, after: number, signal?: AbortSignal): Promise<EventPage> {
  return apiRequest<EventPage>(`${PAST}/${encodeURIComponent(tableId)}/events`, { query: { after, limit: PAST_EVENT_PAGE }, ...(signal ? { signal } : {}) });
}
