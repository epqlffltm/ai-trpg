// web/apps/web/src/pages/chat/conversation/useSnapshots.ts
// 장면 그림(#983)을 읽고 그리기를 시작한다. chat 의 대화와 story 의 장면이 함께 쓴다.
// 그리는 중인 것이 있으면 목록을 몇 초마다 다시 읽는다(서버가 그림을 다 그리면 ready 와 image_id 가 온다).
// 시작한 뒤에는 성공이든 실패든 목록을 다시 읽는다(크레딧이 모자란 것도 실패로 남는다).
// 한 장의 값은 서비스마다 하나라 대화와 상관없이 받아 두고 1분 동안 다시 받지 않는다.

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { drawSnapshot, fetchSnapshotPrice, fetchSnapshots, type SnapshotService } from '../../../api/snapshots';
import { isDrawing, SNAPSHOT_POLL_MS } from './snapshotsView';

function snapshotsKey(service: SnapshotService, conversationId: string) {
  return [service, 'conversation', conversationId, 'snapshots'] as const;
}

/** 값을 다시 받지 않는 동안(ms). 결제 서버의 가격 목록도 1분쯤마다 바뀐다 */
const PRICE_STALE_MS = 60_000;

export function snapshotPriceQuery(service: SnapshotService) {
  return queryOptions({
    queryKey: [service, 'snapshots', 'price'] as const,
    queryFn: ({ signal }) => fetchSnapshotPrice(service, signal),
    staleTime: PRICE_STALE_MS,
  });
}

export function snapshotsQuery(service: SnapshotService, conversationId: string) {
  return queryOptions({
    queryKey: snapshotsKey(service, conversationId),
    queryFn: ({ signal }) => fetchSnapshots(service, conversationId, signal),
    refetchInterval: (query) => (isDrawing(query.state.data ?? []) ? SNAPSHOT_POLL_MS : false),
  });
}

export function useSnapshots(service: SnapshotService, conversationId: string) {
  const queryClient = useQueryClient();
  const snapshots = useQuery(snapshotsQuery(service, conversationId));
  const price = useQuery(snapshotPriceQuery(service)).data;
  const draw = useMutation({
    mutationFn: (messageId: string) => drawSnapshot(service, messageId),
    onSettled: () => queryClient.invalidateQueries({ queryKey: snapshotsKey(service, conversationId) }),
  });
  const list = snapshots.data ?? [];
  // 그리는 중이거나 시작을 기다리는 동안은 새로 그리지 못한다
  const blocked = draw.isPending || isDrawing(list);
  return { list, draw, blocked, price };
}

export type SnapshotsSource = ReturnType<typeof useSnapshots>;
