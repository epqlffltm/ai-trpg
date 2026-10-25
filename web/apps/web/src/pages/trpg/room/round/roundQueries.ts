// web/apps/web/src/pages/trpg/room/round/roundQueries.ts
// 라운드(B6 의 ③)가 읽는 것의 열쇠와 부르는 함수. 지금 라운드와 최근의 라운드들.
// 스트림의 이벤트가 오면 테이블과 함께 묶어서 다시 읽는다(useBatchedRefetch 가 roundsKey 를 버린다).
// 선언을 받는 동안에는 OPEN_POLL_MS 마다도 지금 라운드를 읽는다. 남이 선언을 낸 것(기다리는 사람이 줄어든 것)은
// 아직 이벤트가 없어서다(선언은 마감할 때 player_action 으로 적힌다). 게임 서버가 그 이벤트를 내면 이 읽기를 뺀다.

import { infiniteQueryOptions, queryOptions, type QueryClient } from '@tanstack/react-query';
import { fetchCurrentRound, fetchRecentRounds, fetchRoundsBefore, fetchRoundsFrom, fetchSceneCast } from '../../../../api/rounds';
import type { Round } from '../../../../api/types';

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

/**
 * 선언이나 닫기의 답(그 뒤의 라운드)으로 지금 라운드를 바꾼다.
 * 그 전에 하던 읽기를 멈춘다. 보내기 전에 시작한 읽기(이벤트의 묶은 읽기, 10초 읽기)가 늦게 돌아와
 * 방금 받은 새 라운드를 낡은 것으로 덮지 않게(낸 선언이 사라지고 입력이 다시 열린다).
 */
export async function replaceCurrentRound(queryClient: QueryClient, tableId: string, round: Round): Promise<void> {
  const { queryKey } = currentRoundQuery(tableId);
  await queryClient.cancelQueries({ queryKey, exact: true });
  queryClient.setQueryData(queryKey, round);
}

/**
 * 최근의 라운드들. from 이 없으면 끝의 ROUND_TAIL 개(라운드가 늘면 창이 밀린다).
 * 앞의 라운드를 펼쳤으면 from 번부터 끝까지 읽는다. 창이 밀리지 않아 앞의 라운드(earlierRoundsQuery)와 사이가 비지 않는다
 */
export function recentRoundsQuery(tableId: string, from: number | null = null) {
  return queryOptions({
    queryKey: [...roundsKey(tableId), 'recent', from ?? 'tail'],
    queryFn: ({ signal }) => (from === null ? fetchRecentRounds(tableId, signal) : fetchRoundsFrom(tableId, from, signal)),
  });
}

/**
 * anchor 번 앞의 라운드들(B10). 한 쪽에 ROUND_PAGE 개, 다음 쪽은 앞 쪽의 첫 번호 앞이다. 1 번에 닿으면 끝.
 * 닫힌 라운드는 바뀌지 않는다. 그래서 열쇠를 roundsKey 밖에 두어 이벤트가 와도 다시 읽지 않는다
 */
export function earlierRoundsQuery(tableId: string, anchor: number) {
  return infiniteQueryOptions({
    queryKey: ['trpg', 'tables', tableId, 'round-history', anchor],
    queryFn: ({ pageParam, signal }) => fetchRoundsBefore(tableId, pageParam, signal),
    initialPageParam: anchor,
    getNextPageParam: (lastPage) => {
      const first = lastPage.items[0]?.number;
      return first !== undefined && first > 1 ? first : undefined;
    },
    staleTime: Infinity,
  });
}

/** 지금 장면의 인물과 몬스터. 행동의 대상을 고를 때만 읽는다. 라운드와 함께 버려진다(다음 장면) */
export function sceneCastQuery(tableId: string) {
  return queryOptions({
    queryKey: [...roundsKey(tableId), 'people'],
    queryFn: ({ signal }) => fetchSceneCast(tableId, signal),
  });
}
