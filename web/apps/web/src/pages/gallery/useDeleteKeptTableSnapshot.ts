// web/apps/web/src/pages/gallery/useDeleteKeptTableSnapshot.ts
// 갤러리에서 내 TRPG 장면 그림 한 장을 지운다(#983). 지우면(또는 이미 없으면) 갤러리와 그 테이블의 그림 목록을 다시 읽는다.

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../../api/errors';
import { deleteKeptTableSnapshot, type KeptTableSnapshot } from '../../api/tableSnapshots';
import { tableSnapshotsKey } from '../trpg/room/snapshots/useTableSnapshots';
import { keptTableSnapshotsKey } from './galleryQueries';

export function useDeleteKeptTableSnapshot() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (snapshot: KeptTableSnapshot) => deleteKeptTableSnapshot(snapshot.id),
    onSettled: (_data, error, snapshot) => {
      // 실패해도 이미 없다(404)면 목록이 낡은 것이다
      if (error && !(error instanceof ApiError && error.code === 'snapshot_not_found')) return;
      void queryClient.invalidateQueries({ queryKey: keptTableSnapshotsKey() });
      if (snapshot.table_id) void queryClient.invalidateQueries({ queryKey: tableSnapshotsKey(snapshot.table_id) });
    },
  });
}
