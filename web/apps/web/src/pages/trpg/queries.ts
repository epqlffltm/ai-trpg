// web/apps/web/src/pages/trpg/queries.ts
// TRPG 의 탐색(B1), 소개(B2), 로비(B3), 테이블 만들기(B4)가 읽는 것들의 열쇠와 부르는 함수.
// 공개 목록과 소개는 로그인했는지에 따라 내용이 다르다(로그인 전에는 전체이용가만). 그래서 열쇠에 그것을 넣는다.

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { fetchListing, fetchListings, fetchNarrationModels, type ListingFilters } from '../../api/listings';
import { fetchLobby } from '../../api/tables';

/** 한 쪽에 읽는 수 */
export const PAGE_SIZE = 20;

export function listingsQuery(filters: ListingFilters, signedIn: boolean) {
  return infiniteQueryOptions({
    queryKey: ['trpg', 'listings', 'browse', { ...filters, signedIn }],
    queryFn: ({ pageParam, signal }) => fetchListings(filters, { limit: PAGE_SIZE, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => nextOffset(lastPage.total, allPages.length),
  });
}

/** 다음 쪽의 offset. 다 읽었으면 undefined(더 보기를 숨긴다) */
export function nextOffset(total: number, pagesRead: number): number | undefined {
  const read = pagesRead * PAGE_SIZE;
  return read < total ? read : undefined;
}

/** 로비. 모집 중이고 자리가 남은 공개 테이블. 실시간이 아니라 열 때와 새로 고칠 때 읽는다 */
export function lobbyQuery(scenarioId: string | undefined) {
  return infiniteQueryOptions({
    queryKey: ['trpg', 'tables', 'lobby', { scenarioId }],
    queryFn: ({ pageParam, signal }) => fetchLobby(scenarioId, { limit: PAGE_SIZE, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => nextOffset(lastPage.total, allPages.length),
  });
}

export function listingQuery(scenarioId: string, signedIn: boolean) {
  return queryOptions({
    queryKey: ['trpg', 'listings', 'detail', scenarioId, { signedIn }],
    queryFn: ({ signal }) => fetchListing(scenarioId, signal),
  });
}

/** 서술 모델의 목록. 자주 바뀌지 않아 5분 동안 다시 읽지 않는다 */
export function narrationModelsQuery() {
  return queryOptions({
    queryKey: ['trpg', 'narration-models'],
    queryFn: ({ signal }) => fetchNarrationModels(signal),
    staleTime: 5 * 60 * 1000,
  });
}
