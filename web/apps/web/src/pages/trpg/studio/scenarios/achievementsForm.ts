// web/apps/web/src/pages/trpg/studio/scenarios/achievementsForm.ts
// 시나리오의 업적(B9 업적 탭). 업적 하나의 입력과 업적 목록을 바꾸는 것. 순수한 함수다(서버의 Achievement 를 따른다).
// 제작자가 자기 작품에 다는 것이다(스팀의 업적과 같다). 인증 서버의 활동 배지와는 다른 것이다(docs/architecture/achievements.md).
//
// - 목록의 차례가 시나리오 소개에 보이는 차례다. 50개까지
// - 받는 조건은 퀘스트의 조건과 같은 모양이고 하나 이상이다. 가져가기(consume)는 쓰지 않는다
// - 숨긴 업적은 받기 전에는 이름, 설명, 그림이 가려진다
// - id 는 판이 바뀌어도 그대로 두는 이름표다. 받은 기록이 이것을 가리킨다. 만들 때 정하고(achievement-1 …) 고치지 않는다

import type { Achievement, AchievementBody, QuestMatch } from '../../../../api/types';
import { conditionDrafts, conditionLine, conditionsHints, toConditions, type ConditionDraft, type Targets } from './conditionsForm';

export const MAX_ACHIEVEMENTS = 50;
export const ACHIEVEMENT_NAME_MAX_LENGTH = 40;
export const ACHIEVEMENT_DESCRIPTION_MAX_LENGTH = 200;

export type AchievementDraft = { name: string; description: string; hidden: boolean; imageId: string | null; when: ConditionDraft[]; match: QuestMatch };

export function achievementDraft(achievement: Achievement | undefined): AchievementDraft {
  return {
    name: achievement?.name ?? '',
    description: achievement?.description ?? '',
    hidden: achievement?.hidden ?? false,
    imageId: achievement?.image_id ?? null,
    when: conditionDrafts(achievement?.when ?? []),
    match: achievement?.match ?? 'all',
  };
}

/** 새 업적의 id. 쓰지 않은 achievement-N 가운데 가장 작은 것 */
export function newAchievementId(achievements: Pick<Achievement, 'id'>[]): string {
  const used = new Set(achievements.map((achievement) => achievement.id));
  let number = 1;
  while (used.has(`achievement-${number}`)) number += 1;
  return `achievement-${number}`;
}

export type AchievementHints = { when: Record<number, string>; fields: Record<string, string> };

/** 업적 하나의 문제 */
export function achievementHints(draft: AchievementDraft): AchievementHints {
  const fields: Record<string, string> = {};
  const name = draft.name.trim();
  if (name === '') fields.name = '이름을 적어 주세요.';
  else if (name.length > ACHIEVEMENT_NAME_MAX_LENGTH) fields.name = `이름은 ${ACHIEVEMENT_NAME_MAX_LENGTH}자까지입니다.`;
  if (draft.description.trim().length > ACHIEVEMENT_DESCRIPTION_MAX_LENGTH) fields.description = `받는 법은 ${ACHIEVEMENT_DESCRIPTION_MAX_LENGTH}자까지입니다.`;
  if (draft.when.length === 0) fields.when = '받는 조건을 하나는 적어 주세요.';
  return { when: conditionsHints(draft.when, ''), fields };
}

export function hasAchievementHints(hints: AchievementHints): boolean {
  return Object.keys(hints.when).length > 0 || Object.keys(hints.fields).length > 0;
}

/** 보낼 업적. 가져가기는 보내지 않는다 */
export function toAchievement(id: string, draft: AchievementDraft): AchievementBody {
  return {
    id,
    name: draft.name.trim(),
    description: draft.description.trim(),
    hidden: draft.hidden,
    image_id: draft.imageId,
    when: toConditions(draft.when, false),
    match: draft.match,
  };
}

/** 받은 업적을 보낼 모양으로 */
function asBody(achievement: Achievement): AchievementBody {
  return toAchievement(achievement.id, achievementDraft(achievement));
}

/** 그 업적을 바꾸거나(같은 id) 끝에 더한 목록 */
export function withAchievement(achievements: Achievement[], achievement: AchievementBody): AchievementBody[] {
  const bodies = achievements.map(asBody);
  return bodies.some((one) => one.id === achievement.id) ? bodies.map((one) => (one.id === achievement.id ? achievement : one)) : [...bodies, achievement];
}

/** 그 업적을 지운 목록 */
export function withoutAchievement(achievements: Achievement[], achievementId: string): AchievementBody[] {
  return achievements.map(asBody).filter((one) => one.id !== achievementId);
}

/** 업적을 한 칸 옮길 수 있는가. 목록 안에서만 옮긴다 */
export function canMoveAchievement(length: number, index: number, step: -1 | 1): boolean {
  const target = index + step;
  return target >= 0 && target < length;
}

/** 그 업적을 한 칸 옮긴 목록. 옮길 수 없으면 그대로 */
export function movedAchievement(achievements: Achievement[], index: number, step: -1 | 1): AchievementBody[] {
  const bodies = achievements.map(asBody);
  if (!canMoveAchievement(achievements.length, index, step)) return bodies;
  const target = index + step;
  [bodies[index], bodies[target]] = [bodies[target]!, bodies[index]!];
  return bodies;
}

/** 목록의 한 줄. "숨김 · 그림 있음 · 받는 조건: 종탑에 닿는다 그리고 「구울 사냥」 성공" */
export function achievementLine(achievement: Achievement, targets: Targets): string {
  const when = achievement.when.map((one) => conditionLine(one, targets)).join(achievement.match === 'all' ? ' 그리고 ' : ' 또는 ');
  const marks = [achievement.hidden ? '숨김' : '', achievement.image_id ? '그림 있음' : ''].filter(Boolean);
  return [...marks, `받는 조건: ${when}`].join(' · ');
}
