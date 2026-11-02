// web/apps/web/src/api/search.ts
// 작품 검색(#984). 시나리오(게임 서버), 캐릭터와 세계관(asset 서버)의 공개 목록에 검색어(q)를 실어 서버마다 따로 부른다(#593).
// 모아 주는 서버를 두지 않고, 서버 사이에 섞어 정렬하지 않는다. 한 서버가 답하지 않으면 그 묶음만 빈다.
// 로그인하지 않아도 부른다. 그때는 전체이용가만 온다(#530).

import { apiRequest } from './http';
import type { PublicWorldPage } from './storyWorlds';
import type { PublicCharacterPage, PublicListingPage } from './types';

/** 검색 결과의 한 묶음(서비스 하나)에 싣는 수 */
export const SEARCH_LIMIT = 20;

/** TRPG 의 시나리오. 제목이나 한 줄 소개, 또는 "#태그" */
export function searchScenarios(q: string, signal?: AbortSignal): Promise<PublicListingPage> {
  return apiRequest<PublicListingPage>('/api/v1/game/listings', { query: { q, limit: SEARCH_LIMIT }, ...withSignal(signal) });
}

/** chat 의 캐릭터. 마지막 판의 이름, 또는 "#태그" */
export function searchCharacters(q: string, signal?: AbortSignal): Promise<PublicCharacterPage> {
  return apiRequest<PublicCharacterPage>('/api/v1/asset/listings/characters', {
    query: { q, limit: SEARCH_LIMIT },
    ...withSignal(signal),
  });
}

/** story 의 세계관. 마지막 판의 이름, 또는 "#태그" */
export function searchWorlds(q: string, signal?: AbortSignal): Promise<PublicWorldPage> {
  return apiRequest<PublicWorldPage>('/api/v1/asset/listings/worlds', { query: { q, limit: SEARCH_LIMIT }, ...withSignal(signal) });
}

function withSignal(signal: AbortSignal | undefined): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}
