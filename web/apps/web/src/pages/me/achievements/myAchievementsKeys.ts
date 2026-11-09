// web/apps/web/src/pages/me/achievements/myAchievementsKeys.ts
// 마이페이지 "작품 업적"의 읽기 열쇠. 업적을 받는 화면(TRPG 테이블 방, story 세션, chat 대화)이 받은 순간 이 열쇠를 다시 읽게 한다.
// 열쇠만 둔다(읽는 함수는 myAchievementsQueries.ts). 받는 화면이 마이페이지의 모듈을 끌어오지 않게 따로 둔다.

import type { AchievementService } from './myAchievementsView';

export const MY_WORK_ACHIEVEMENTS_KEY = ['me', 'work-achievements'] as const;

/** 그 서비스의 "작품 업적" 열쇠 */
export function myWorkAchievementsKey(service: AchievementService) {
  return [...MY_WORK_ACHIEVEMENTS_KEY, service] as const;
}
