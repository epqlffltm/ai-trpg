// web/apps/web/src/api/storyWorlds.ts
// story 의 세계관(asset 서버). 내 세계관(/asset/worlds)과 공개 세계관의 목록과 소개(/asset/listings/worlds, D1).
// 공개 목록과 소개는 로그인하지 않아도 읽는다(그때는 전체이용가만). 볼 수 없으면 404 다.
// 소개는 판의 문서를 통째로 주지 않는다. 인물은 보임이면 이름과 그림, 실루엣이면 둘 다 null, 숨김이면 빠진다. 엔딩은 기록에 남는 수만.
// 세션은 게시한 판(latest_version)이 있는 세계관으로만 시작한다. 판의 문서(WorldDocument)는 세션 읽기에도 실린다.
// 만들기와 게시는 1~2단계에 운영자만이다(403 operator_only). 인물은 자기 캐릭터만(422 character_not_owned).
// 게시는 막는 것이 있으면 409 {problems} 다. 성공하면 새 판과 알리는 것(warnings), 소개에서 걸러 낸 것(removed)이 온다.
// 제작 도구(D7)는 초안을 읽고(GET), 보낸 칸만 고치고(PATCH, null 은 그림·시작 장소·시작 시간대·기한만), 지우고, 게시 점검과 판의 목록을 읽는다.

import type { components } from './generated/asset';
import { apiRequest } from './http';

type Schemas = components['schemas'];
export type StoryWorldPage = Schemas['WorldPage'];
export type StoryWorldSummary = Schemas['WorldSummary'];
export type StoryWorldDocument = Schemas['WorldDocument'];
export type StoryWorldCreate = Schemas['WorldCreate'];
export type StoryWorldDetail = Schemas['WorldDetail'];
export type StoryWorldPublished = Schemas['WorldPublishResult'];
export type StoryWorldUpdate = Schemas['WorldUpdate'];
export type StoryWorldCheck = Schemas['WorldPublishCheck'];
export type StoryWorldVersion = Schemas['WorldVersionSummary'];
export type StoryWorldPlace = Schemas['WorldPlace'];
export type StoryWorldItem = Schemas['WorldItem'];
export type StoryWorldSlot = Schemas['Slot'];
export type StoryWorldShow = Schemas['Show'];
export type StoryWorldCast = Schemas['CastMember'];
export type StoryWorldConditions = Schemas['Conditions'];
export type StoryWorldCondition = Schemas['Condition'];
export type StoryWorldConditionKind = Schemas['ConditionKind'];
export type StoryWorldEffect = Schemas['Effect'];
export type StoryWorldEffectKind = Schemas['EffectKind'];
export type StoryWorldScene = Schemas['Scene'];
export type StoryWorldEvent = Schemas['Event'];
export type StoryWorldEnding = Schemas['Ending'];
export type PublicWorldPage = Schemas['PublicWorldPage'];
export type PublicWorldSummary = Schemas['PublicWorldSummary'];
export type PublicWorldDetail = Schemas['PublicWorldDetail'];
export type PublicCastMember = Schemas['PublicCastMember'];

/** 한 번에 읽는 내 세계관의 수(서버는 100 까지) */
export const MY_WORLDS_LIMIT = 100;

export function fetchMyStoryWorlds(signal?: AbortSignal): Promise<StoryWorldPage> {
  return apiRequest<StoryWorldPage>('/api/v1/asset/worlds', { query: { limit: MY_WORLDS_LIMIT, offset: 0 }, ...(signal ? { signal } : {}) });
}

/** 만들 때 보내는 값. 이름만 필수이고 나머지는 서버의 기본값이다 */
export type StoryWorldCreateBody = Pick<StoryWorldCreate, 'name'> & Partial<StoryWorldCreate>;

/** 세계관 만들기. 처음에는 비공개 초안이다 */
export function createStoryWorld(body: StoryWorldCreateBody): Promise<StoryWorldDetail> {
  return apiRequest<StoryWorldDetail>('/api/v1/asset/worlds', { method: 'POST', body });
}

function worldPath(worldId: string): string {
  return `/api/v1/asset/worlds/${encodeURIComponent(worldId)}`;
}

function withSignal(signal?: AbortSignal): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

/** 내 세계관 하나(초안) */
export function fetchStoryWorld(worldId: string, signal?: AbortSignal): Promise<StoryWorldDetail> {
  return apiRequest<StoryWorldDetail>(worldPath(worldId), withSignal(signal));
}

/** 보낸 칸만 고친다. 게시한 판은 그대로다 */
export function updateStoryWorld(worldId: string, body: StoryWorldUpdate): Promise<StoryWorldDetail> {
  return apiRequest<StoryWorldDetail>(worldPath(worldId), { method: 'PATCH', body });
}

export function deleteStoryWorld(worldId: string): Promise<void> {
  return apiRequest<void>(worldPath(worldId), { method: 'DELETE' });
}

/** 지금 게시하면 막히는 것, 알리는 것, 소개에서 걸러질 것. 판을 만들지 않는다 */
export function fetchStoryWorldCheck(worldId: string, signal?: AbortSignal): Promise<StoryWorldCheck> {
  return apiRequest<StoryWorldCheck>(`${worldPath(worldId)}/publish-check`, withSignal(signal));
}

export function fetchStoryWorldVersions(worldId: string, signal?: AbortSignal): Promise<StoryWorldVersion[]> {
  return apiRequest<StoryWorldVersion[]>(`${worldPath(worldId)}/versions`, withSignal(signal));
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
