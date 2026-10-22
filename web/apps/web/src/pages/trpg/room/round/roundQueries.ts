// web/apps/web/src/pages/trpg/room/round/roundQueries.ts
// 라운드(B6 의 ③)가 읽는 것의 열쇠와 부르는 함수. 지금 라운드와 최근의 라운드들.
// 스트림의 이벤트가 오면 테이블과 함께 묶어서 다시 읽는다(useBatchedRefetch 가 roundsKey 를 버린다).
// 선언을 받는 동안에는 OPEN_POLL_MS 마다도 지금 라운드를 읽는다. 남이 선언을 낸 것(기다리는 사람이 줄어든 것)은
// 아직 이벤트가 없어서다(선언은 마감할 때 player_action 으로 적힌다). 게임 서버가 그 이벤트를 내면 이 읽기를 뺀다.

import { queryOptions } from '@tanstack/react-query';
import { fetchCurrentRound, fetchRecentRounds } from '../../../../api/rounds';

/** 선언을 받는 동안 지금 라운드를 다시 읽는 사이 */
export const OPEN_POLL_MS = 10_000;

/** 이 테이블의 라운드 읽기 모두의 앞부분. 한꺼번에 버릴 때 쓴다 */
export function roundsKey(tableId: string) {
  return ['trpg', 'tables', tableId, 'rounds'] as const;
}

export function currentRoundQuery(tableId: string) {
  return queryOptions({
    queryKey: [...roundsKey(tableId), 'current'],
    queryFn: ({ signal }) => fetchCurrentRound(tableId, signal),
    refetchInterval: (query) => (query.state.data?.status === 'open' ? OPEN_POLL_MS : false),
  });
}

export function recentRoundsQuery(tableId: string) {
  return queryOptions({
    queryKey: [...roundsKey(tableId), 'recent'],
    queryFn: ({ signal }) => fetchRecentRounds(tableId, signal),
  });
}
