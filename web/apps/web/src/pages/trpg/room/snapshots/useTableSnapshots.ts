// web/apps/web/src/pages/trpg/room/snapshots/useTableSnapshots.ts
// 테이블의 장면 그림(#983)을 읽고 그리기를 시작한다. 방의 라운드(RoundStage)가 한 번 부르고 라운드마다 나눠 준다.
//   - 목록의 열쇠는 라운드의 열쇠(roundsKey) 아래다. 스트림의 이벤트로 테이블과 라운드를 다시 읽을 때 함께 다시 읽는다
//   - 그리는 중인 것이 있으면 몇 초마다 다시 읽는다. 남이 그리기 시작한 것은 알림이 없어 다음에 다시 읽을 때 보인다
//   - 시작한 뒤에는 성공이든 실패든 목록을 다시 읽는다(크레딧이 모자란 것도 실패로 남는다). 404 면 테이블도 다시 읽는다
//   - 한 장의 값은 테이블과 상관없이 받아 두고 1분 동안 다시 받지 않는다

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../../../../api/errors';
import { drawTableSnapshot, fetchTableSnapshotPrice, fetchTableSnapshots } from '../../../../api/tableSnapshots';
import { SNAPSHOT_POLL_MS } from '../../../chat/conversation/snapshotsView';
import { tableQuery } from '../roomQueries';
import { roundsKey } from '../round/roundQueries';
import { isTableDrawing } from './tableSnapshotsView';

/** 값을 다시 받지 않는 동안(ms). 결제 서버의 가격 목록도 1분쯤마다 바뀐다 */
const PRICE_STALE_MS = 60_000;

export function tableSnapshotsKey(tableId: string) {
  return [...roundsKey(tableId), 'snapshots'] as const;
}

export function tableSnapshotsQuery(tableId: string) {
  return queryOptions({
    queryKey: tableSnapshotsKey(tableId),
    queryFn: ({ signal }) => fetchTableSnapshots(tableId, signal),
    refetchInterval: (query) => (isTableDrawing(query.state.data ?? []) ? SNAPSHOT_POLL_MS : false),
  });
}

export function tableSnapshotPriceQuery() {
  return queryOptions({
    queryKey: ['trpg', 'snapshots', 'price'] as const,
    queryFn: ({ signal }) => fetchTableSnapshotPrice(signal),
    staleTime: PRICE_STALE_MS,
  });
}

export function useTableSnapshots(tableId: string) {
  const queryClient = useQueryClient();
  const snapshots = useQuery(tableSnapshotsQuery(tableId));
  const price = useQuery(tableSnapshotPriceQuery()).data;
  const draw = useMutation({
    mutationFn: (roundNumber: number) => drawTableSnapshot(tableId, roundNumber),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 404) void queryClient.invalidateQueries({ queryKey: tableQuery(tableId).queryKey });
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: tableSnapshotsKey(tableId) }),
  });
  const list = snapshots.data ?? [];
  // 그리는 중이거나 시작을 기다리는 동안은 새로 그리지 못한다
  const blocked = draw.isPending || isTableDrawing(list);
  return { list, draw, blocked, price };
}

export type TableSnapshotsSource = ReturnType<typeof useTableSnapshots>;
