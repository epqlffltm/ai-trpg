// web/apps/web/src/pages/trpg/studio/worlds/worldQueries.ts
// 세계관 하나의 읽기(B9). 목록은 재료가 함께 쓴다(studioQueries.ts).

import { queryOptions } from '@tanstack/react-query';
import { fetchWorld } from '../../../../api/worlds';
import { assetDetailKey } from '../studioQueries';

export function worldQuery(worldId: string) {
  return queryOptions({
    queryKey: assetDetailKey('worlds', worldId),
    queryFn: ({ signal }) => fetchWorld(worldId, signal),
  });
}
