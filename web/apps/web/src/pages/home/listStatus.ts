// web/apps/web/src/pages/home/listStatus.ts
// 읽기(useQuery)의 상태를 목록 한 줄의 상태로 바꾼다. 화면을 그리지 않는 순수한 함수다.

import type { ListStatus } from '@ai-trpg/ui';

type QueryLike = { isPending: boolean; isError: boolean };

export function listStatus(query: QueryLike, itemCount: number): ListStatus {
  if (query.isPending) return 'loading';
  if (query.isError) return 'error';
  return itemCount === 0 ? 'empty' : 'ready';
}
