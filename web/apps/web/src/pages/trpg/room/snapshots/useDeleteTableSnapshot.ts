// web/apps/web/src/pages/trpg/room/snapshots/useDeleteTableSnapshot.ts
// 내가 그린 테이블의 장면 그림 한 장을 지운다(#983). 지우면(또는 이미 없으면) 그 테이블의 그림 목록을 다시 읽는다.
// 다른 사람의 화면은 서버가 스트림에 알려(scene_snapshot) 다시 읽는다.

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../../../../api/errors';
import { deleteTableSnapshot } from '../../../../api/tableSnapshots';
import { tableSnapshotsKey } from './useTableSnapshots';

export function useDeleteTableSnapshot(tableId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (snapshotId: string) => deleteTableSnapshot(tableId, snapshotId),
    onSettled: (_data, error) => {
      // 실패해도 이미 없다(404)면 목록이 낡은 것이다
      if (error && !(error instanceof ApiError && error.code === 'snapshot_not_found')) return;
      void queryClient.invalidateQueries({ queryKey: tableSnapshotsKey(tableId) });
    },
  });
}
