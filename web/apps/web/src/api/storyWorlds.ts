// web/apps/web/src/api/storyWorlds.ts
// story 의 세계관(asset 서버). 내 세계관(/asset/worlds)과 공개 세계관의 목록과 소개(/asset/listings/worlds, D1).
// 공개 목록과 소개는 로그인하지 않아도 읽는다(그때는 전체이용가만). 볼 수 없으면 404 다.
// 소개는 판의 문서를 통째로 주지 않는다. 인물은 보임이면 이름과 그림, 실루엣이면 둘 다 null, 숨김이면 빠진다. 엔딩은 기록에 남는 수만.
// 세션은 게시한 판(latest_version)이 있는 세계관으로만 시작한다. 판의 문서(WorldDocument)는 세션 읽기에도 실린다.
// 만들기와 게시는 1~2단계에 운영자만이다(403 operator_only). 인물은 자기 캐릭터만(422 character_not_owned).
// 게시는 막는 것이 있으면 409 {problems} 다. 성공하면 새 판과 알리는 것(warnings), 소개에서 걸러 낸 것(removed)이 온다.

import type { components } from './generated/asset';
import { apiRequest } from './http';

type Schemas = components['schemas'];
export type StoryWorldPage = Schemas['WorldPage'];
export type StoryWorldSummary = Schemas['WorldSummary'];
export type StoryWorldDocument = Schemas['WorldDocument'];
export type StoryWorldCreate = Schemas['WorldCreate'];
export type StoryWorldDetail = Schemas['WorldDetail'];
export type StoryWorldPublished = Schemas['WorldPublishResult'];
export type PublicWorldPage = Schemas['PublicWorldPage'];
export type PublicWorldSummary = Schemas['PublicWorldSummary'];
export type PublicWorldDetail = Schemas['PublicWorldDetail'];
export type PublicCastMember = Schemas['PublicCastMember'];

/** 한 번에 읽는 내 세계관의 수(서버는 100 까지) */
export const MY_WORLDS_LIMIT = 100;

export function fetchMyStoryWorlds(signal?: AbortSignal): Promise<StoryWorldPage> {
  return apiRequest<StoryWorldPage>('/api/v1/asset/worlds', { query: { limit: MY_WORLDS_LIMIT, offset: 0 }, ...(signal ? { signal } : {}) });
}

/** 세계관 만들기. 처음에는 비공개 초안이다 */
export function createStoryWorld(body: StoryWorldCreate): Promise<StoryWorldDetail> {
  return apiRequest<StoryWorldDetail>('/api/v1/asset/worlds', { method: 'POST', body });
}

/** 지금의 초안을 새 판으로 게시한다 */
export function publishStoryWorld(worldId: string, note: string): Promise<StoryWorldPublished> {
  return apiRequest<StoryWorldPublished>(`/api/v1/asset/worlds/${encodeURIComponent(worldId)}/versions`, { method: 'POST', body: note ? { note } : {} });
}

/** 공개 세계관. 최근에 게시한 것부터 */
export function fetchPublicWorlds(paging: { limit: number; offset: number }, signal?: AbortSignal): Promise<PublicWorldPage> {
  return apiRequest<PublicWorldPage>('/api/v1/asset/listings/worlds', { query: paging, ...(signal ? { signal } : {}) });
}

export function fetchPublicWorld(worldId: string, signal?: AbortSignal): Promise<PublicWorldDetail> {
  return apiRequest<PublicWorldDetail>(`/api/v1/asset/listings/worlds/${encodeURIComponent(worldId)}`, signal ? { signal } : {});
}
