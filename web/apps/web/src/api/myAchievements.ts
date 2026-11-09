// web/apps/web/src/api/myAchievements.ts
// 내가 받은 작품 업적(#193, docs/architecture/achievements.md). 제작자가 작품에 단 업적이고, 인증 서버의 활동 배지와는 다르다.
// 서비스마다 그 서버가 기록을 갖는다. 모든 작품의 것을 받은 때가 늦은 것부터 한 쪽씩 준다(?limit=&offset=).
//   - TRPG(trpg 서버): GET /api/v1/game/achievements/mine. 시나리오의 지금 제목과, 지금 공개 중이고 볼 수 있는지(listed)
//   - story(story 서버): GET /api/v1/story/achievements/mine. 세계관의 이름은 내가 가져온 마지막 판의 것
//   - chat(chat 서버): GET /api/v1/chat/achievements/mine. 캐릭터의 이름은 내가 가져온 마지막 판의 것
// 로그인해야 부른다. 화면은 읽기만 한다(업적을 주는 것은 엔진이다).

import type { components as Chat } from './generated/chat';
import type { components as Story } from './generated/story';
import type { components as Trpg } from './generated/trpg';
import { apiRequest } from './http';

export type MyScenarioAchievementPage = Trpg['schemas']['MyAchievementPage'];
export type MyScenarioAchievement = Trpg['schemas']['MyAchievementOut'];
export type MyStoryAchievementPage = Story['schemas']['MyAchievementPage'];
export type MyStoryAchievement = Story['schemas']['MyAchievementOut'];
export type MyChatAchievementPage = Chat['schemas']['MyAchievementPage'];
export type MyChatAchievement = Chat['schemas']['MyAchievementOut'];

/** 한 쪽에 싣는 수 */
export const MY_ACHIEVEMENT_PAGE_SIZE = 20;

function page(offset: number, signal?: AbortSignal) {
  return { query: { limit: MY_ACHIEVEMENT_PAGE_SIZE, offset }, ...(signal ? { signal } : {}) };
}

export function fetchMyScenarioAchievements(offset: number, signal?: AbortSignal): Promise<MyScenarioAchievementPage> {
  return apiRequest<MyScenarioAchievementPage>('/api/v1/game/achievements/mine', page(offset, signal));
}

export function fetchMyStoryAchievements(offset: number, signal?: AbortSignal): Promise<MyStoryAchievementPage> {
  return apiRequest<MyStoryAchievementPage>('/api/v1/story/achievements/mine', page(offset, signal));
}

export function fetchMyChatAchievements(offset: number, signal?: AbortSignal): Promise<MyChatAchievementPage> {
  return apiRequest<MyChatAchievementPage>('/api/v1/chat/achievements/mine', page(offset, signal));
}
