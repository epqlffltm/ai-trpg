// web/apps/web/src/pages/trpg/studio/scenarios/conditionsForm.ts
// 퀘스트와 사건의 조건(B9 퀘스트·사건 탭). 순수한 함수다(서버의 QuestCondition 과 QuestRule·HappeningRule 의 검사를 따른다).
//
// - 종류마다 대상이 다르다: 장소, 몬스터(시트를 적은 것), 물건, 인물, 다른 퀘스트(사건 항목)
// - 개수(1~99)는 몬스터 쓰러뜨리기, 물건 지니기, 물건 잃기만 쓴다. 가져가기(consume)는 퀘스트의 이루는 조건의 물건 지니기만
// - 퀘스트 잇기(성공했다, 실패했다)는 드러나는 조건과 실패하는 조건, 사건의 조건에 쓴다. 자기 자신은 가리키지 못한다
// - 물건 잃기는 실패하는 조건과 사건의 조건에만 쓴다
// - 캠페인의 앞 편의 퀘스트(campaign_quest_succeeded, campaign_quest_failed, #481 B)는 아직 고르는 칸이 없다. 받은 대로 보인다
// - 한 목록에 같은 종류의 같은 대상은 한 줄, 5 줄까지
// - 장(chapter_at_least, #481)은 대상(target) 대신 장의 id(chapter)를 적는다. 시나리오의 장 가운데서 고른다(Targets.chapters).
//   장이 없는 시나리오에서는 고를 수 없다(withChapterKind). 장의 넘어오는 조건에는 쓰지 않는다(서버도 받지 않는다)

import type { QuestCondition, QuestConditionBody, QuestConditionKind } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';
import type { EntryChoice } from './useLoreEntries';

export const MAX_CONDITIONS = 5;
export const CONDITION_MAX_COUNT = 99;

const KIND_LABELS: Record<QuestConditionKind, string> = {
  reach_place: '장소에 닿는다',
  defeat_monster: '몬스터를 쓰러뜨린다',
  hold_item: '물건을 지닌다',
  defeat_npc: '인물이 쓰러진다',
  npc_dead: '인물이 죽는다',
  lose_item: '물건을 잃는다(지닌 것이 개수보다 적다)',
  quest_succeeded: '다른 퀘스트가 성공했다',
  quest_failed: '다른 퀘스트가 실패했다',
  chapter_at_least: '지금 장이 그 장 이상이다',
  campaign_quest_succeeded: '캠페인의 앞 편에서 그 퀘스트가 성공했다',
  campaign_quest_failed: '캠페인의 앞 편에서 그 퀘스트가 실패했다',
};

/** 조건의 대상의 종류 */
export type TargetKind = 'places' | 'monsters' | 'items' | 'npcs' | 'quests';

// 장(chapter_at_least)은 대상이 없다. 장의 id 를 적는다
const TARGETS: Record<Exclude<QuestConditionKind, 'chapter_at_least'>, TargetKind> = {
  reach_place: 'places',
  defeat_monster: 'monsters',
  hold_item: 'items',
  defeat_npc: 'npcs',
  npc_dead: 'npcs',
  lose_item: 'items',
  quest_succeeded: 'quests',
  quest_failed: 'quests',
  // 캠페인의 앞 편의 퀘스트(#481 B)는 이 시나리오 밖의 사건이다. 고르는 칸은 캠페인 화면과 함께 더한다(KINDS_FOR 에 없다).
  // 이미 적힌 조건의 한 줄은 이 시나리오의 퀘스트에서 이름을 찾고, 없으면 찾을 수 없다고 보인다
  campaign_quest_succeeded: 'quests',
  campaign_quest_failed: 'quests',
};

const COUNTED: QuestConditionKind[] = ['defeat_monster', 'hold_item', 'lose_item'];
const LINKS: QuestConditionKind[] = ['quest_succeeded', 'quest_failed'];

/** 조건의 목록마다 쓸 수 있는 종류 */
export const KINDS_FOR = {
  /** 퀘스트를 이루는 조건 */
  goal: ['reach_place', 'defeat_monster', 'hold_item', 'defeat_npc', 'npc_dead'],
  /** 숨긴 퀘스트가 드러나는 조건 */
  reveal: ['reach_place', 'defeat_monster', 'hold_item', 'defeat_npc', 'npc_dead', 'quest_succeeded', 'quest_failed'],
  /** 퀘스트가 실패하는 조건, 사건의 조건 */
  any: ['reach_place', 'defeat_monster', 'hold_item', 'defeat_npc', 'npc_dead', 'lose_item', 'quest_succeeded', 'quest_failed'],
} satisfies Record<string, QuestConditionKind[]>;

/** 고를 대상들. 종류마다 이름이 있는 목록이다. chapters 는 장(chapter_at_least)이 고르는 시나리오의 장(id, 이름)이다 */
export type Targets = Record<TargetKind, EntryChoice[]> & { chapters?: EntryChoice[] };

/** 장이 있는 시나리오면 그 목록의 종류에 장(chapter_at_least)을 더한다. 장이 없으면 그대로 */
export function withChapterKind(kinds: QuestConditionKind[], targets: Targets): QuestConditionKind[] {
  return (targets.chapters ?? []).length > 0 ? [...kinds, 'chapter_at_least'] : kinds;
}

export function kindLabel(kind: QuestConditionKind): string {
  return KIND_LABELS[kind];
}

/** 그 종류의 대상의 종류. 장(chapter_at_least)은 대상이 없어 null 이다 */
export function targetKindOf(kind: QuestConditionKind): TargetKind | null {
  return kind === 'chapter_at_least' ? null : TARGETS[kind];
}

export function isCounted(kind: QuestConditionKind): boolean {
  return COUNTED.includes(kind);
}

/** 조건 한 줄의 초안. chapter 는 장(chapter_at_least)일 때만 쓴다 */
export type ConditionDraft = { kind: QuestConditionKind; target: string; chapter?: string; count: string; consume: boolean };

export function conditionDrafts(conditions: QuestCondition[]): ConditionDraft[] {
  return conditions.map((condition) => ({
    kind: condition.kind,
    target: condition.target ?? '',
    chapter: condition.chapter ?? '',
    count: String(condition.count),
    consume: condition.consume,
  }));
}

/** 새 조건. 그 목록이 쓸 수 있는 첫 종류 */
export function newCondition(kinds: QuestConditionKind[]): ConditionDraft {
  return { kind: kinds[0] ?? 'reach_place', target: '', chapter: '', count: '1', consume: false };
}

/** 종류를 바꾸면 대상과 장, 개수, 가져가기를 비운다(대상의 종류가 바뀐다) */
export function withKind(kind: QuestConditionKind): ConditionDraft {
  return { kind, target: '', chapter: '', count: '1', consume: false };
}

/** 조건마다의 문제. 차례 → 글. selfId 는 이 퀘스트·사건의 사건 항목(자기 자신을 가리키지 못한다) */
export function conditionsHints(drafts: ConditionDraft[], selfId: string): Record<number, string> {
  const hints: Record<number, string> = {};
  drafts.forEach((draft, index) => {
    if (draft.kind === 'chapter_at_least') {
      if (!draft.chapter) hints[index] = '장을 골라 주세요.';
    } else if (draft.target === '') hints[index] = '대상을 골라 주세요.';
    else if (LINKS.includes(draft.kind) && draft.target === selfId) hints[index] = '자기 자신을 가리킬 수 없습니다.';
    else if (drafts.findIndex((other) => other.kind === draft.kind && other.target === draft.target && (other.chapter ?? '') === (draft.chapter ?? '')) !== index)
      hints[index] = '같은 조건이 위에 있습니다.';
    else if (isCounted(draft.kind) && wholeNumber(draft.count, 1, CONDITION_MAX_COUNT) === null) hints[index] = `개수는 1~${CONDITION_MAX_COUNT} 사이의 정수입니다.`;
  });
  return hints;
}

/** 보낼 조건들. 세지 않는 조건은 개수 1, 가져가기는 allowConsume 이고 물건 지니기일 때만 */
export function toConditions(drafts: ConditionDraft[], allowConsume: boolean): QuestConditionBody[] {
  return drafts.map((draft) =>
    draft.kind === 'chapter_at_least'
      ? { kind: draft.kind, chapter: draft.chapter ?? '', count: 1, consume: false }
      : {
          kind: draft.kind,
          target: draft.target,
          count: isCounted(draft.kind) ? Number(draft.count.trim()) : 1,
          consume: allowConsume && draft.kind === 'hold_item' && draft.consume,
        },
  );
}

/** 장의 이름(「축제」). 시나리오에 없는 장이면 적힌 id 를 그대로 */
function chapterName(chapter: string | null | undefined, targets: Targets): string {
  const found = (targets.chapters ?? []).find((one) => one.id === chapter);
  return found ? `「${found.name}」` : `「${chapter ?? '?'}」(찾을 수 없음)`;
}

/** 조건 한 줄. "구울 3마리를 쓰러뜨린다", "수도원 문에 닿는다", "「축제」 장 이상" */
export function conditionLine(condition: Pick<QuestCondition, 'kind' | 'target' | 'chapter' | 'count' | 'consume'>, targets: Targets): string {
  const kind = targetKindOf(condition.kind);
  const name = (kind ? targets[kind].find((one) => one.id === condition.target)?.name : undefined) ?? '(찾을 수 없음)';
  switch (condition.kind) {
    case 'reach_place':
      return `${name}에 닿는다`;
    case 'defeat_monster':
      return `${name} ${condition.count}마리를 쓰러뜨린다`;
    case 'hold_item':
      return `${name} ${condition.count}개를 지닌다${condition.consume ? '(가져감)' : ''}`;
    case 'lose_item':
      return `지닌 ${name} ${condition.count}개 미만`;
    case 'defeat_npc':
      return `${name} 쓰러짐`;
    case 'npc_dead':
      return `${name} 죽음`;
    case 'quest_succeeded':
      return `「${name}」 성공`;
    case 'quest_failed':
      return `「${name}」 실패`;
    case 'chapter_at_least':
      return `${chapterName(condition.chapter, targets)} 장 이상`;
    case 'campaign_quest_succeeded':
      return `앞 편에서 「${name}」 성공`;
    case 'campaign_quest_failed':
      return `앞 편에서 「${name}」 실패`;
  }
}
