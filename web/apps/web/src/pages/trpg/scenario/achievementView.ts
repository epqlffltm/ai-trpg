// web/apps/web/src/pages/trpg/scenario/achievementView.ts
// 시나리오 업적을 보이는 데 쓰는 순수한 함수들. 화면을 그리지 않는다.

import type { ScenarioAchievement } from '../../../api/achievements';
import { formatDate } from '../../../format/dateTime';

/** 숨긴 업적을 받기 전의 이름 */
export const HIDDEN_NAME = '숨긴 업적';

/** 업적의 이름. 숨긴 업적을 받기 전이면 "숨긴 업적" */
export function achievementName(achievement: ScenarioAchievement): string {
  return achievement.name ?? HIDDEN_NAME;
}

/** 업적의 받는 법. 숨긴 업적을 받기 전이면 그렇다고 적는다. 받는 법을 적지 않았으면 null */
export function achievementDescription(achievement: ScenarioAchievement): string | null {
  if (achievement.name === null) return '받으면 이름과 받는 법이 보입니다.';
  return achievement.description ? achievement.description : null;
}

/**
 * 달성률의 글. "플레이한 12명 중 3명(25%)". 플레이한 사람이 없으면 그렇다고 적는다.
 * 0 보다 크고 1% 보다 작으면 "1% 미만"이다(0% 로 보이면 아무도 받지 않은 것처럼 읽힌다).
 */
export function achievementRate(earnedCount: number, players: number): string {
  if (players <= 0) return '아직 플레이한 사람이 없습니다';
  const ratio = (earnedCount / players) * 100;
  const percent = ratio > 0 && ratio < 1 ? '1% 미만' : `${Math.round(ratio)}%`;
  return `플레이한 ${players}명 중 ${earnedCount}명(${percent})`;
}

/** 내가 받은 때의 글. 받지 않았으면 null */
export function earnedLine(achievement: ScenarioAchievement): string | null {
  return achievement.earned_at ? `${formatDate(achievement.earned_at)}에 받음` : null;
}

/** 받은 수의 한 줄. 로그인했을 때만 뜻이 있다 */
export function mineLine(items: ScenarioAchievement[]): string {
  return `내가 받은 업적 ${items.filter((item) => item.earned_at).length} / ${items.length}개`;
}
