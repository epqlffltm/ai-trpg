// web/apps/web/src/pages/trpg/portraits/portraitQueries.ts
// 내가 올린 캐릭터 그림(#983)의 읽기. 목록은 쪽마다 더 읽고, 그림의 바이트는 한 번 받으면 다시 받지 않는다(그림은 바뀌지 않는다).

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { fetchPortraitImage, fetchPortraits, PORTRAIT_PAGE_SIZE } from '../../../api/portraits';

export function portraitsKey() {
  return ['game', 'portraits'] as const;
}

export function portraitsQuery() {
  return infiniteQueryOptions({
    queryKey: portraitsKey(),
    queryFn: ({ pageParam, signal }) => fetchPortraits(pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) => {
      const read = pages.length * PORTRAIT_PAGE_SIZE;
      return read < lastPage.total ? read : undefined;
    },
  });
}

export function portraitImageQuery(portraitId: string) {
  return queryOptions({
    queryKey: [...portraitsKey(), portraitId, 'image'] as const,
    queryFn: ({ signal }) => fetchPortraitImage(portraitId, signal),
    staleTime: Infinity,
  });
}
