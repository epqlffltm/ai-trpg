// web/apps/web/src/api/creators.ts
// 제작자(#992). 프로필(표시 이름과 소개)은 인증 서버, 공개 작품은 그 작품의 서버(게임, asset)가 준다(#593).
// 제작자 페이지는 서버마다 따로 부르고 섞어 정렬하지 않는다. 로그인하지 않아도 부른다(전체이용가만 온다).
// 공개 작품에는 공개 목록처럼 보는 사람의 설정(성인 작품 숨김, 성향)을 싣는다(listingPreferences.ts).
//   - GET /auth/creators/{id}: 없거나 탈퇴한 제작자는 404 creator_not_found
//   - GET /auth/creators?q=: 닉네임으로 찾기(#984). 소개를 쓴 사람만이다. 검색어는 1~20자(닉네임의 상한)
//   - PATCH /auth/me/profile: 내 소개. 200자를 넘으면 400

import type { components } from './generated/auth';
import { apiRequest } from './http';
import { listingPreferences } from './listingPreferences';
import type { PublicWorldPage } from './storyWorlds';
import type { PublicCharacterPage, PublicListingPage } from './types';

export type Creator = components['schemas']['Creator'];
export type MyProfile = components['schemas']['MyProfile'];
export type CreatorSearchResult = components['schemas']['CreatorSearchResult'];

/** 제작자를 찾는 검색어의 길이 상한. 닉네임의 상한과 같다(인증 서버) */
export const CREATOR_SEARCH_MAX_LENGTH = 20;
/** 검색 결과에 보일 제작자의 수 */
export const CREATOR_SEARCH_LIMIT = 10;

/** 제작자 소개의 길이 상한(인증 서버와 같다) */
export const BIO_MAX_LENGTH = 200;

/** 제작자 페이지에서 서비스마다 보일 작품의 수 */
export const CREATOR_WORKS_LIMIT = 20;

function withSignal(signal: AbortSignal | undefined): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

export function fetchCreator(publicId: string, signal?: AbortSignal): Promise<Creator> {
  return apiRequest<Creator>(`/api/v1/auth/creators/${encodeURIComponent(publicId)}`, { skipRefresh: true, ...withSignal(signal) });
}

/** 닉네임에 q 가 든 제작자. 닉네임이 같은 것, 그것으로 시작하는 것, 나머지 차례다 */
export function searchCreators(q: string, signal?: AbortSignal): Promise<CreatorSearchResult> {
  return apiRequest<CreatorSearchResult>('/api/v1/auth/creators', {
    query: { q, limit: CREATOR_SEARCH_LIMIT },
    skipRefresh: true,
    ...withSignal(signal),
  });
}

export function updateMyProfile(changes: MyProfile): Promise<MyProfile> {
  return apiRequest<MyProfile>('/api/v1/auth/me/profile', { method: 'PATCH', body: changes });
}

/** 그 사람의 공개 시나리오(TRPG) */
export function fetchCreatorScenarios(publicId: string, signal?: AbortSignal): Promise<PublicListingPage> {
  return apiRequest<PublicListingPage>('/api/v1/game/listings', {
    query: { creator: publicId, limit: CREATOR_WORKS_LIMIT, ...listingPreferences() },
    ...withSignal(signal),
  });
}

/** 그 사람의 공개 캐릭터(chat) */
export function fetchCreatorCharacters(publicId: string, signal?: AbortSignal): Promise<PublicCharacterPage> {
  return apiRequest<PublicCharacterPage>('/api/v1/asset/listings/characters', {
    query: { creator: publicId, limit: CREATOR_WORKS_LIMIT, ...listingPreferences() },
    ...withSignal(signal),
  });
}

/** 그 사람의 공개 세계관(story) */
export function fetchCreatorWorlds(publicId: string, signal?: AbortSignal): Promise<PublicWorldPage> {
  return apiRequest<PublicWorldPage>('/api/v1/asset/listings/worlds', {
    query: { creator: publicId, limit: CREATOR_WORKS_LIMIT, ...listingPreferences() },
    ...withSignal(signal),
  });
}
