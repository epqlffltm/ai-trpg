// web/apps/web/src/pages/trpg/room/roomQueries.ts
// 테이블 방(B6)이 읽는 것의 열쇠와 부르는 함수. 테이블 하나, 채팅, 일어난 일(이벤트).
// 채팅과 일어난 일은 처음에 끝부분만 읽고 그 뒤는 스트림이 더한다. 그래서 스스로 다시 읽지 않는다(staleTime 무한).
// 테이블은 스트림의 이벤트가 오면 묶어서 다시 읽는다(useBatchedRefetch). 이벤트로 값을 고치지 않는다(화면 명세 B7 의 "다시 읽기").
// 모집 중에는 RECRUITING_POLL_MS 마다도 읽는다. 남이 캐릭터를 정한 것(PUT .../character)은 아직 이벤트가 없어서다.
// 게임 서버가 그 이벤트를 내면 이 읽기를 뺀다.
// 바꾸는 요청이 돌려준 테이블은 putTable 로 넣는다. 그 요청보다 먼저 떠난 읽기(바뀌기 전의 테이블)가 나중에 닿아
// 방금 넣은 것을 덮지 못하게 한다(queryClient.ts 의 putQueryData). 그냥 setQueryData 하면 느린 망에서 고친 것이 잠깐 되돌아간다.

import { queryOptions, type QueryClient } from '@tanstack/react-query';
import { fetchChatTail, fetchEventsTail, fetchTable } from '../../../api/tableRoom';
import type { TableDetail } from '../../../api/types';
import { putQueryData } from '../../../queryClient';

/** 모집 중에 테이블을 다시 읽는 사이(남의 캐릭터, 프리젠을 누가 가져갔는지) */
export const RECRUITING_POLL_MS = 15_000;

export function tableQuery(tableId: string) {
  return queryOptions({
    queryKey: ['trpg', 'tables', tableId, 'detail'],
    queryFn: ({ signal }) => fetchTable(tableId, signal),
    refetchInterval: (query) => (query.state.data?.status === 'recruiting' ? RECRUITING_POLL_MS : false),
  });
}

/**
 * 바꾸는 요청이 돌려준 테이블을 넣는다. 그보다 먼저 떠나 아직 오는 중인 테이블의 읽기는 멈춘다(바뀌기 전의 것이다).
 * 답이 테이블 전체라서 멈춘 읽기를 다시 하지 않는다(#975)
 */
export function putTable(queryClient: QueryClient, table: TableDetail): Promise<void> {
  return putQueryData(queryClient, tableQuery(table.id).queryKey, table, { whole: true });
}

export function chatQuery(tableId: string) {
  return queryOptions({
    queryKey: ['trpg', 'tables', tableId, 'chat'],
    queryFn: ({ signal }) => fetchChatTail(tableId, signal),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

export function eventsQuery(tableId: string) {
  return queryOptions({
    queryKey: ['trpg', 'tables', tableId, 'events'],
    queryFn: ({ signal }) => fetchEventsTail(tableId, signal),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}
