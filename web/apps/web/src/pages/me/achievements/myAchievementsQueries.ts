// web/apps/web/src/pages/me/achievements/myAchievementsQueries.ts
// 마이페이지 "작품 업적"의 읽기. 서비스마다 열쇠가 따로다(고른 서비스의 서버만 부른다). 쪽은 받은 그대로 한 모양의 줄로 바꿔 둔다.
// 열쇠는 ['me', 'work-achievements', 서비스] 다(myAchievementsKeys.ts). 업적을 받는 화면(테이블 방, 세션, 대화)이 받은 순간 다시 읽게 한다.

import { infiniteQueryOptions } from '@tanstack/react-query';
import { fetchMyChatAchievements, fetchMyScenarioAchievements, fetchMyStoryAchievements, MY_ACHIEVEMENT_PAGE_SIZE } from '../../../api/myAchievements';
import { myWorkAchievementsKey } from './myAchievementsKeys';
import { chatLine, nextAchievementOffset, scenarioLine, storyLine, type AchievementService, type MyAchievementLine } from './myAchievementsView';

/** 한 쪽. 줄과 모든 수 */
export type MyAchievementLines = { lines: MyAchievementLine[]; total: number };

async function fetchLines(service: AchievementService, offset: number, signal: AbortSignal): Promise<MyAchievementLines> {
  if (service === 'trpg') {
    const page = await fetchMyScenarioAchievements(offset, signal);
    return { lines: page.items.map(scenarioLine), total: page.total };
  }
  if (service === 'story') {
    const page = await fetchMyStoryAchievements(offset, signal);
    return { lines: page.items.map(storyLine), total: page.total };
  }
  const page = await fetchMyChatAchievements(offset, signal);
  return { lines: page.items.map(chatLine), total: page.total };
}

export function myAchievementsQuery(service: AchievementService) {
  return infiniteQueryOptions({
    queryKey: myWorkAchievementsKey(service),
    queryFn: ({ pageParam, signal }) => fetchLines(service, pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) => nextAchievementOffset(pages.length * MY_ACHIEVEMENT_PAGE_SIZE, lastPage.total),
  });
}
