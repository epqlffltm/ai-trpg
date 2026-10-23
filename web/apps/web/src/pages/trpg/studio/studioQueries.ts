// web/apps/web/src/pages/trpg/studio/studioQueries.ts
// 제작 도구(B9)가 읽는 것의 열쇠. 재료마다 ['trpg', 'studio', <종류>] 아래에 목록(list)과 낱개(detail)를 둔다.
// 열쇠의 앞을 무르면 목록과 낱개가 함께 다시 읽힌다.

import { infiniteQueryOptions } from '@tanstack/react-query';
import { fetchAssets, type StudioKind } from '../../../api/studio';
import { nextOffset, PAGE_SIZE } from '../queries';

export function studioKey(kind: StudioKind) {
  return ['trpg', 'studio', kind] as const;
}

export function assetListKey(kind: StudioKind) {
  return [...studioKey(kind), 'list'] as const;
}

export function assetDetailKey(kind: StudioKind, assetId: string) {
  return [...studioKey(kind), 'detail', assetId] as const;
}

/** 내 재료의 목록. 최근에 만든 것부터 한 쪽씩 */
export function assetsQuery(kind: StudioKind) {
  return infiniteQueryOptions({
    queryKey: assetListKey(kind),
    queryFn: ({ pageParam, signal }) => fetchAssets(kind, { limit: PAGE_SIZE, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => nextOffset(lastPage.total, allPages.length),
  });
}
