// web/apps/web/src/api/listings.ts
// 게임 서버의 공개 시나리오(B1 탐색, B2 소개)와 고를 수 있는 서술 모델.
// 공개 목록과 소개는 로그인하지 않아도 부른다. 그때는 토큰이 없어 전체이용가만 온다(#530). 성인용은 없는 것(목록에서 빠지고 소개는 404)이다.

import { apiRequest } from './http';
import type { Genre, NarrationModels, PublicListingDetail, PublicListingPage } from './types';

const GAME = '/api/v1/game';

/** 목록을 거르는 조건. 함께 걸면 모두 맞는 것만 온다. 비운 것은 보내지 않는다 */
export type ListingFilters = {
  genre?: Genre | undefined;
  tag?: string | undefined;
  players?: number | undefined;
};

/** 공개 시나리오의 한 쪽. 최근 공개한 것부터(순서는 고를 수 없다) */
export function fetchListings(
  filters: ListingFilters,
  page: { limit: number; offset: number },
  signal?: AbortSignal,
): Promise<PublicListingPage> {
  return apiRequest<PublicListingPage>(`${GAME}/listings`, {
    query: { ...page, genre: filters.genre, tag: filters.tag, players: filters.players },
    ...(signal ? { signal } : {}),
  });
}

/** 공개 시나리오 하나와 테이블을 만들기 전에 고를 것들. 볼 수 없으면 404 */
export function fetchListing(scenarioId: string, signal?: AbortSignal): Promise<PublicListingDetail> {
  return apiRequest<PublicListingDetail>(`${GAME}/listings/${encodeURIComponent(scenarioId)}`, signal ? { signal } : {});
}

/** 테이블의 서술 모델로 고를 수 있는 것과 값. 로그인한 사람에게만 보인다 */
export function fetchNarrationModels(signal?: AbortSignal): Promise<NarrationModels> {
  return apiRequest<NarrationModels>(`${GAME}/tables/narration-models`, signal ? { signal } : {});
}
