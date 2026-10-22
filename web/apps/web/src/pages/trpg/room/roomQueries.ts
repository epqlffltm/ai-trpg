// web/apps/web/src/pages/trpg/room/roomQueries.ts
// 테이블 방(B6)이 읽는 것의 열쇠와 부르는 함수. 테이블 하나와 채팅.
// 채팅은 처음에 끝부분만 읽고 그 뒤는 스트림이 더한다. 그래서 스스로 다시 읽지 않는다(staleTime 무한).
// 테이블은 스트림의 이벤트가 오면 묶어서 다시 읽는다(useBatchedRefetch). 이벤트로 값을 고치지 않는다(화면 명세 B7 의 "다시 읽기").
// 모집 중에는 RECRUITING_POLL_MS 마다도 읽는다. 남이 캐릭터를 정한 것(PUT .../character)은 아직 이벤트가 없어서다.
// 게임 서버가 그 이벤트를 내면 이 읽기를 뺀다.

import { queryOptions } from '@tanstack/react-query';
import { fetchChatTail, fetchTable } from '../../../api/tableRoom';

/** 모집 중에 테이블을 다시 읽는 사이(남의 캐릭터, 프리젠을 누가 가져갔는지) */
export const RECRUITING_POLL_MS = 15_000;

export function tableQuery(tableId: string) {
  return queryOptions({
    queryKey: ['trpg', 'tables', tableId, 'detail'],
    queryFn: ({ signal }) => fetchTable(tableId, signal),
    refetchInterval: (query) => (query.state.data?.status === 'recruiting' ? RECRUITING_POLL_MS : false),
  });
}

export function chatQuery(tableId: string) {
  return queryOptions({
    queryKey: ['trpg', 'tables', tableId, 'chat'],
    queryFn: ({ signal }) => fetchChatTail(tableId, signal),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}
