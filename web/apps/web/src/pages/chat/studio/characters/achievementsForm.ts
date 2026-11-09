// web/apps/web/src/pages/chat/studio/characters/achievementsForm.ts
// 캐릭터의 업적 탭의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/characters/schemas.py 의 CharacterAchievement,
// docs/architecture/achievements.md 의 "chat").
//
//   - 업적은 50 개까지이고 적은 차례가 소개에 보이는 차례다. id 는 화면이 붙이고 판이 바뀌어도 그대로 둔다(받은 기록이 가리킨다)
//   - 이름(40자)은 꼭 적는다. 받는 법(200자)은 고른다. 숨긴 업적은 받기 전에 이름, 받는 법, 그림을 가린다
//   - 받는 조건은 1~5 개이고 모두(all) 또는 하나라도(any) 맞으면 받는다. 종류마다 쓰는 칸이 다르다(KIND_FIELDS)
//   - 대상(장소, 물건, 이벤트 씬, 호감도 단계)은 저장한 것에서 고른다. 종류를 바꾸면 대상과 수를 비운다

import type {
  AssetAchievementCondition,
  AssetAchievementKind,
  AssetAchievementMatch,
  AssetCharacterAchievement,
  AssetCharacterDetail,
  AssetCharacterUpdate,
} from '../../../../api/types';

export const ACHIEVEMENTS_MAX = 50;
export const ACHIEVEMENT_NAME_MAX = 40;
export const ACHIEVEMENT_DESCRIPTION_MAX = 200;
export const ACHIEVEMENT_CONDITIONS_MAX = 5;
export const ACHIEVEMENT_COUNT_MAX = 9999;

/** 종류마다 쓰는 칸. target 은 장소·물건·이벤트 씬의 id, value 는 호감도 단계의 이름, count 는 물건의 수나 보낸 말의 수 */
export const KIND_FIELDS: Record<AssetAchievementKind, { target: boolean; value: boolean; count: boolean }> = {
  visited_place: { target: true, value: false, count: false },
  hold_item: { target: true, value: false, count: true },
  received_item: { target: true, value: false, count: false },
  affection_stage: { target: false, value: true, count: false },
  scene_seen: { target: true, value: false, count: false },
  messages_at_least: { target: false, value: false, count: true },
};

/** 조건 하나의 입력. 수는 입력 칸의 글이다 */
export type ConditionDraft = { kind: AssetAchievementKind; target: string; value: string; count: string };

export type AchievementDraft = {
  id: string;
  name: string;
  description: string;
  hidden: boolean;
  imageId: string | null;
  match: AssetAchievementMatch;
  items: ConditionDraft[];
};

export const EMPTY_CONDITION: ConditionDraft = { kind: 'visited_place', target: '', value: '', count: '1' };

function conditionDraft(condition: AssetAchievementCondition): ConditionDraft {
  return { kind: condition.kind, target: condition.target ?? '', value: condition.value ?? '', count: String(condition.count ?? 1) };
}

export function achievementDraft(achievement: AssetCharacterAchievement): AchievementDraft {
  return {
    id: achievement.id,
    name: achievement.name,
    description: achievement.description ?? '',
    hidden: achievement.hidden ?? false,
    imageId: achievement.image_id ?? null,
    match: achievement.when.match ?? 'all',
    items: achievement.when.items.map(conditionDraft),
  };
}

export function achievementDrafts(character: Pick<AssetCharacterDetail, 'achievements'>): AchievementDraft[] {
  return (character.achievements ?? []).map(achievementDraft);
}

export function addAchievement(achievements: AchievementDraft[], id: string): AchievementDraft[] {
  if (achievements.length >= ACHIEVEMENTS_MAX) return achievements;
  return [...achievements, { id, name: '', description: '', hidden: false, imageId: null, match: 'all', items: [EMPTY_CONDITION] }];
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

export function addCondition(achievement: AchievementDraft): AchievementDraft {
  if (achievement.items.length >= ACHIEVEMENT_CONDITIONS_MAX) return achievement;
  return { ...achievement, items: [...achievement.items, EMPTY_CONDITION] };
}

/** 조건 하나를 바꾼다. 종류가 바뀌면 대상과 수를 비운다(장소, 물건, 씬, 단계는 서로 다른 것이다) */
export function changeCondition(achievement: AchievementDraft, index: number, changes: Partial<ConditionDraft>): AchievementDraft {
  const items = achievement.items.map((item, at) => {
    if (at !== index) return item;
    const next = { ...item, ...changes };
    return changes.kind && changes.kind !== item.kind ? { ...EMPTY_CONDITION, kind: changes.kind } : next;
  });
  return { ...achievement, items };
}

export function removeCondition(achievement: AchievementDraft, index: number): AchievementDraft {
  return { ...achievement, items: achievement.items.filter((_, at) => at !== index) };
}

/** 고를 수 있는 것 하나(값과 보이는 이름) */
export type Choice = { value: string; label: string };

/** 조건의 종류마다 고를 수 있는 대상. 저장한 장소, 물건, 이벤트 씬, 호감도 단계에서 고른다. 보낸 말의 수는 고를 것이 없다 */
export function conditionChoices(character: AssetCharacterDetail, kind: AssetAchievementKind): Choice[] {
  if (kind === 'visited_place') return character.places.map((place, index) => ({ value: place.id, label: place.name || `장소 ${index + 1}` }));
  if (kind === 'hold_item' || kind === 'received_item') return character.items.map((item, index) => ({ value: item.id, label: item.name || `물건 ${index + 1}` }));
  if (kind === 'scene_seen') return character.event_scenes.map((scene, index) => ({ value: scene.id, label: scene.title || `이벤트 씬 ${index + 1}` }));
  if (kind === 'affection_stage') return (character.affection?.stages ?? []).map((stage) => ({ value: stage.name, label: stage.name }));
  return [];
}

/** 수 칸의 글이 1~9999 의 정수인가 */
function isCount(text: string): boolean {
  if (!/^\d+$/.test(text.trim())) return false;
  const count = Number(text.trim());
  return count >= 1 && count <= ACHIEVEMENT_COUNT_MAX;
}

function conditionHint(condition: ConditionDraft): string | null {
  const fields = KIND_FIELDS[condition.kind];
  if (fields.target && condition.target === '') return '대상을 골라 주세요.';
  if (fields.value && condition.value === '') return '호감도의 단계를 골라 주세요.';
  if (fields.count && !isCount(condition.count)) return `수는 1~${ACHIEVEMENT_COUNT_MAX} 사이의 정수로 적어 주세요.`;
  return null;
}

export type AchievementHints = { name?: string; description?: string; when?: string; conditions: Record<number, string> };

function achievementHints(achievement: AchievementDraft): AchievementHints {
  const conditions: Record<number, string> = {};
  achievement.items.forEach((item, index) => {
    const hint = conditionHint(item);
    if (hint) conditions[index] = hint;
  });
  const hints: AchievementHints = { conditions };
  const name = achievement.name.trim();
  if (name === '') hints.name = '이름을 적어 주세요.';
  else if (name.length > ACHIEVEMENT_NAME_MAX) hints.name = `이름은 ${ACHIEVEMENT_NAME_MAX}자까지입니다.`;
  if (achievement.description.trim().length > ACHIEVEMENT_DESCRIPTION_MAX) hints.description = `받는 법은 ${ACHIEVEMENT_DESCRIPTION_MAX}자까지입니다.`;
  if (achievement.items.length === 0) hints.when = '받는 조건을 하나 이상 적어 주세요.';
  return hints;
}

export function achievementsHints(achievements: AchievementDraft[]): Record<string, AchievementHints> {
  const hints: Record<string, AchievementHints> = {};
  for (const achievement of achievements) hints[achievement.id] = achievementHints(achievement);
  return hints;
}

export function hasAchievementsHints(hints: Record<string, AchievementHints>): boolean {
  return Object.values(hints).some((entry) => Boolean(entry.name || entry.description || entry.when) || Object.keys(entry.conditions).length > 0);
}

/**
 * 조건 하나를 보낼 모양으로. 그 종류가 쓰는 target, value 만 보낸다(쓰지 않는 칸을 보내면 서버가 422 다).
 * count 를 쓰지 않는 종류는 1 이다(서버의 기본값이고, 1 이면 받는다)
 */
export function toCondition(condition: ConditionDraft): AssetAchievementCondition {
  const fields = KIND_FIELDS[condition.kind];
  return {
    kind: condition.kind,
    ...(fields.target ? { target: condition.target } : {}),
    ...(fields.value ? { value: condition.value } : {}),
    count: fields.count ? Number(condition.count.trim()) : 1,
  };
}

/** 업적 탭의 칸만 보낸다. 힌트가 없을 때만 부른다 */
export function toAchievementsBody(achievements: AchievementDraft[]): AssetCharacterUpdate {
  return {
    achievements: achievements.map((achievement) => ({
      id: achievement.id,
      name: achievement.name.trim(),
      description: achievement.description.trim(),
      hidden: achievement.hidden,
      image_id: achievement.imageId,
      when: { match: achievement.match, items: achievement.items.map(toCondition) },
    })),
  };
}
