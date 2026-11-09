// web/apps/web/src/pages/story/studio/achievementsForm.ts
// 세계관의 업적 탭의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/worlds/schemas.py 의 Achievement,
// docs/architecture/achievements.md 의 "story").
//
//   - 업적은 50 개까지이고 적은 차례가 세계관 소개에 보이는 차례다. id 는 화면이 붙이고 판이 바뀌어도 그대로 둔다(받은 기록이 가리킨다)
//   - 이름(40자)은 꼭 적는다. 받는 법(200자)은 고른다. 숨긴 업적은 받기 전에 이름, 받는 법, 그림을 가린다
//   - 받는 조건은 이벤트의 조건과 같은 모양이고 하나 이상 적는다(비면 늘 맞아 첫 행동에 그냥 받는다)

import type { StoryWorldAchievement, StoryWorldDetail, StoryWorldUpdate } from '../../../api/storyWorlds';
import { conditionsDraft, conditionsHints, EMPTY_CONDITIONS, toConditions, type ConditionChoices, type ConditionsDraft } from './conditionsForm';

export const ACHIEVEMENTS_MAX = 50;
export const ACHIEVEMENT_NAME_MAX = 40;
export const ACHIEVEMENT_DESCRIPTION_MAX = 200;

export type AchievementDraft = { id: string; name: string; description: string; hidden: boolean; imageId: string | null; when: ConditionsDraft };

export function achievementDraft(achievement: StoryWorldAchievement): AchievementDraft {
  return {
    id: achievement.id,
    name: achievement.name,
    description: achievement.description,
    hidden: achievement.hidden,
    imageId: achievement.image_id ?? null,
    when: conditionsDraft(achievement.when),
  };
}

export function achievementDrafts(world: Pick<StoryWorldDetail, 'achievements'>): AchievementDraft[] {
  return (world.achievements ?? []).map(achievementDraft);
}

export function addAchievement(achievements: AchievementDraft[], id: string): AchievementDraft[] {
  if (achievements.length >= ACHIEVEMENTS_MAX) return achievements;
  return [...achievements, { id, name: '', description: '', hidden: false, imageId: null, when: EMPTY_CONDITIONS }];
}

export function changeAchievement(achievements: AchievementDraft[], id: string, change: (achievement: AchievementDraft) => AchievementDraft): AchievementDraft[] {
  return achievements.map((achievement) => (achievement.id === id ? change(achievement) : achievement));
}

export function removeAchievement(achievements: AchievementDraft[], id: string): AchievementDraft[] {
  return achievements.filter((achievement) => achievement.id !== id);
}

export function moveAchievementUp(achievements: AchievementDraft[], index: number): AchievementDraft[] {
  if (index <= 0 || index >= achievements.length) return achievements;
  const next = [...achievements];
  [next[index - 1], next[index]] = [next[index] as AchievementDraft, next[index - 1] as AchievementDraft];
  return next;
}

export type AchievementHints = { name?: string; description?: string; when?: string; conditions: Record<number, string> };

function achievementHints(achievement: AchievementDraft, choices: ConditionChoices): AchievementHints {
  const hints: AchievementHints = { conditions: conditionsHints(achievement.when, choices) };
  const name = achievement.name.trim();
  if (name === '') hints.name = '이름을 적어 주세요.';
  else if (name.length > ACHIEVEMENT_NAME_MAX) hints.name = `이름은 ${ACHIEVEMENT_NAME_MAX}자까지입니다.`;
  if (achievement.description.trim().length > ACHIEVEMENT_DESCRIPTION_MAX) hints.description = `받는 법은 ${ACHIEVEMENT_DESCRIPTION_MAX}자까지입니다.`;
  if (achievement.when.items.length === 0) hints.when = '받는 조건을 하나 이상 적어 주세요.';
  return hints;
}

export function achievementsHints(achievements: AchievementDraft[], choices: ConditionChoices): Record<string, AchievementHints> {
  const hints: Record<string, AchievementHints> = {};
  for (const achievement of achievements) hints[achievement.id] = achievementHints(achievement, choices);
  return hints;
}

export function hasAchievementsHints(hints: Record<string, AchievementHints>): boolean {
  return Object.values(hints).some((entry) => Boolean(entry.name || entry.description || entry.when) || Object.keys(entry.conditions).length > 0);
}

/** 업적 탭의 칸만 보낸다. 힌트가 없을 때만 부른다 */
export function toAchievementsBody(achievements: AchievementDraft[]): StoryWorldUpdate {
  return {
    achievements: achievements.map((achievement) => ({
      id: achievement.id,
      name: achievement.name.trim(),
      description: achievement.description.trim(),
      hidden: achievement.hidden,
      image_id: achievement.imageId,
      when: toConditions(achievement.when),
    })),
  };
}
