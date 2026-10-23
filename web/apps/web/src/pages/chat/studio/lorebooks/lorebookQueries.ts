// web/apps/web/src/pages/chat/studio/lorebooks/lorebookQueries.ts
// chat 의 로어북이 읽는 것의 열쇠. 모두 ['chat', 'studio', 'lorebooks'] 아래에 둔다.
// 목록(list), 고르기 목록(picker), 낱개(detail)가 있고 판의 목록은 낱개 아래에 둔다.
// 저장하면 낱개는 받은 것으로 바꾸고 목록을 무른다. 게시하면 낱개(latest_version)와 판, 목록을 다시 읽는다.

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { fetchLorebook, fetchLorebookVersions, fetchMyLorebooks } from '../../../../api/assetLorebooks';
import { nextOffset, PAGE_SIZE } from '../characters/characterQueries';

/** 캐릭터의 로어북 탭이 고를 때 한 번에 읽는 수(서버의 한 쪽의 상한) */
export const PICKER_SIZE = 100;

export const LOREBOOKS_KEY = ['chat', 'studio', 'lorebooks'] as const;

export function lorebookListKey() {
  return [...LOREBOOKS_KEY, 'list'] as const;
}

export function lorebookPickerKey() {
  return [...LOREBOOKS_KEY, 'picker'] as const;
}

export function lorebookKey(lorebookId: string) {
  return [...LOREBOOKS_KEY, 'detail', lorebookId] as const;
}

export function lorebookVersionsKey(lorebookId: string) {
  return [...lorebookKey(lorebookId), 'versions'] as const;
}

export function myLorebooksQuery() {
  return infiniteQueryOptions({
    queryKey: lorebookListKey(),
    queryFn: ({ pageParam, signal }) => fetchMyLorebooks({ limit: PAGE_SIZE, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => nextOffset(lastPage.total, allPages.length),
  });
}

/** 캐릭터에 붙일 때 고르는 목록. 최근에 고친 것부터 한 쪽(100 개)만 읽는다 */
export function lorebookPickerQuery() {
  return queryOptions({
    queryKey: lorebookPickerKey(),
    queryFn: ({ signal }) => fetchMyLorebooks({ limit: PICKER_SIZE, offset: 0 }, signal),
  });
}

export function lorebookQuery(lorebookId: string) {
  return queryOptions({
    queryKey: lorebookKey(lorebookId),
    queryFn: ({ signal }) => fetchLorebook(lorebookId, signal),
  });
}

export function lorebookVersionsQuery(lorebookId: string) {
  return queryOptions({
    queryKey: lorebookVersionsKey(lorebookId),
    queryFn: ({ signal }) => fetchLorebookVersions(lorebookId, signal),
  });
}
