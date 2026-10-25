// web/apps/web/src/pages/trpg/past/pastQueries.ts
// 떠난 테이블(B10)이 읽는 것. 떠난 뒤의 기록은 바뀌지 않아 다시 읽지 않는다(staleTime: Infinity).

import { infiniteQueryOptions } from '@tanstack/react-query';
import { fetchPastEvents, fetchPastTables, PAST_TABLE_PAGE } from '../../../api/pastTables';

const PAST_KEY = ['trpg', 'past-tables'] as const;

/** 떠난 테이블의 목록. 쪽마다 PAST_TABLE_PAGE 개, total 에 닿으면 끝 */
export function pastTablesQuery() {
  return infiniteQueryOptions({
    queryKey: [...PAST_KEY, 'list'],
    queryFn: ({ pageParam, signal }) => fetchPastTables(pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) => {
      const read = pages.length * PAST_TABLE_PAGE;
      return read < lastPage.total ? read : undefined;
    },
  });
}

/** 떠난 테이블의 이벤트. 처음부터 한 묶음씩, 떠났다는 이벤트(last_sequence)에 닿으면 끝 */
export function pastEventsQuery(tableId: string) {
  return infiniteQueryOptions({
    queryKey: [...PAST_KEY, 'events', tableId],
    queryFn: ({ pageParam, signal }) => fetchPastEvents(tableId, pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const last = lastPage.items.at(-1)?.sequence;
      return last !== undefined && last < lastPage.last_sequence ? last : undefined;
    },
    staleTime: Infinity,
  });
}
