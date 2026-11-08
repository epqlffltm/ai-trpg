// web/apps/web/src/api/achievements.ts
// 시나리오 업적(게임 서버, docs/architecture/achievements.md). 제작자가 작품에 다는 업적이다. 인증 서버의 활동 배지와는 다르다.
//   - 공개된 시나리오의 업적을 판의 차례로 받는다. 로그인하지 않아도 읽는다(그때는 내가 받은 때가 없다)
//   - 숨긴 업적은 내가 받기 전에는 이름, 설명, 그림이 null 이다. 조건은 오지 않는다
//   - 받은 수(earned_count)와 플레이한 사람의 수(players)가 온다. 달성률은 화면이 나눈다
// 실패: 404(볼 수 없는 시나리오)

import type { components as Trpg } from './generated/trpg';
import { apiRequest } from './http';

export type ScenarioAchievements = Trpg['schemas']['ScenarioAchievements'];
export type ScenarioAchievement = Trpg['schemas']['ScenarioAchievementOut'];

/** 공개된 시나리오의 업적들과 받은 수 */
export function fetchScenarioAchievements(scenarioId: string, signal?: AbortSignal): Promise<ScenarioAchievements> {
  const path = `/api/v1/game/listings/${encodeURIComponent(scenarioId)}/achievements`;
  return apiRequest<ScenarioAchievements>(path, signal ? { signal } : {});
}
