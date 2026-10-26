// web/apps/web/src/api/storyWorlds.ts
// story 의 세계관(asset 서버의 /asset/worlds). 지금은 내 세계관만 읽는다. 남에게 공개된 세계관의 목록은 asset 서버에 아직 없다.
// 세션은 게시한 판(latest_version)이 있는 세계관으로만 시작한다. 판의 문서(WorldDocument)는 세션 읽기에도 실린다.

import type { components } from './generated/asset';
import { apiRequest } from './http';

type Schemas = components['schemas'];
export type StoryWorldPage = Schemas['WorldPage'];
export type StoryWorldSummary = Schemas['WorldSummary'];
export type StoryWorldDocument = Schemas['WorldDocument'];

/** 한 번에 읽는 내 세계관의 수(서버는 100 까지) */
export const MY_WORLDS_LIMIT = 100;

export function fetchMyStoryWorlds(signal?: AbortSignal): Promise<StoryWorldPage> {
  return apiRequest<StoryWorldPage>('/api/v1/asset/worlds', { query: { limit: MY_WORLDS_LIMIT, offset: 0 }, ...(signal ? { signal } : {}) });
}
