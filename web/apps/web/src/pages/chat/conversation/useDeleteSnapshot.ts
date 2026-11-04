// web/apps/web/src/pages/chat/conversation/useDeleteSnapshot.ts
// 장면 그림 한 장을 지운다(#983). chat 과 story, 말 아래와 갤러리가 함께 쓴다.
// 지우면(또는 이미 없으면) 그 서비스의 대화마다의 그림 목록과 갤러리의 목록을 다시 읽는다.

import { useMutation, useQueryClient, type Query } from '@tanstack/react-query';
import { ApiError } from '../../../api/errors';
import { deleteSnapshot, type SnapshotService } from '../../../api/snapshots';

/** 그 서비스의 그림 목록인가. 대화마다의 것([service, 'conversation', id, 'snapshots'])과 갤러리의 것([service, 'snapshots', 'kept']) */
export function isSnapshotList(service: SnapshotService, query: Pick<Query, 'queryKey'>): boolean {
  const [head, kind, third, fourth] = query.queryKey as readonly unknown[];
  if (head !== service) return false;
  return (kind === 'conversation' && fourth === 'snapshots') || (kind === 'snapshots' && third === 'kept');
}

export function useDeleteSnapshot(service: SnapshotService) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (snapshotId: string) => deleteSnapshot(service, snapshotId),
    onSettled: (_data, error) => {
      // 실패해도 이미 없다(404)면 목록이 낡은 것이다
      if (error && !(error instanceof ApiError && error.code === 'snapshot_not_found')) return;
      void queryClient.invalidateQueries({ predicate: (query) => isSnapshotList(service, query) });
    },
  });
}
