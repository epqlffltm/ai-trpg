// web/apps/web/src/pages/gallery/galleryQueries.ts
// 갤러리(C7)가 읽는 것. 연 기록은 쪽으로 이어 읽고, 캐릭터의 판은 잘 바뀌지 않아 5분 동안 다시 읽지 않는다.

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { fetchChatUnlocks, fetchPublicCharacter, UNLOCK_PAGE_SIZE } from '../../api/gallery';
import { isClientError } from '../../api/http';

export function chatUnlocksQuery() {
  return infiniteQueryOptions({
    queryKey: ['chat', 'gallery'],
    queryFn: ({ pageParam, signal }) => fetchChatUnlocks(pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) => {
      const read = pages.length * UNLOCK_PAGE_SIZE;
      return read < lastPage.total ? read : undefined;
    },
  });
}

/** 캐릭터의 공개 판. 404(공개를 내림, 숨김)는 다시 묻지 않는다 */
export function publicCharacterQuery(id: string) {
  return queryOptions({
    queryKey: ['asset', 'listing', 'character', id],
    queryFn: ({ signal }) => fetchPublicCharacter(id, signal),
    staleTime: 5 * 60 * 1000,
    retry: (count, error) => !isClientError(error) && count < 2,
  });
}
