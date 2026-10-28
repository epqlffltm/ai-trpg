// web/apps/web/src/pages/story/studio/conditionsForm.ts
// 조건 목록(일정의 줄, 고백, 이벤트, 엔딩이 같은 모양을 쓴다)의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/worlds/schemas.py 의 Condition).
//
//   - 조건은 종류마다 쓰는 칸이 다르다(CONDITION_FIELDS). 쓰지 않는 칸은 보내지 않는다(수는 1 로 보낸다, 서버의 "세지 않음")
//   - 대상은 표에서 고른다(글로 식을 적지 않는다). 고를 거리(장소, 물건, 인물과 그 단계, 시간대, 이벤트)는 쓰는 쪽이 넘긴다
//   - 종류를 바꾸면 대상과 값을 비우고, 호감도의 인물을 바꾸면 단계를 비운다
//   - 고를 거리에 없는 대상(그사이 지운 장소, 인물)은 다시 고르라고 알린다
//   - 목록은 10 개까지이고, 모두 맞아야 하는가(all) 하나라도 맞으면 되는가(any)

import type { StoryWorldCondition, StoryWorldConditionKind, StoryWorldConditions } from '../../../api/storyWorlds';

export const CONDITIONS_MAX = 10;
export const CONDITION_COUNT_MAX = 365;
const UNCOUNTED = 1;

type Field = 'target' | 'value' | 'count';
/** 대상이 무엇의 id 인가. 값(value)은 물건의 id 나 그 인물의 호감도 단계의 이름이다 */
type TargetKind = 'place' | 'item' | 'cast' | 'slot' | 'event';

type KindSpec = { label: string; fields: Field[]; target?: TargetKind; value?: 'item' | 'stage'; count?: string };

export const CONDITION_KINDS: Record<StoryWorldConditionKind, KindSpec> = {
  reach_place: { label: '그 장소에 있다', fields: ['target'], target: 'place' },
  hold_item: { label: '그 물건을 몇 개 이상 가졌다', fields: ['target', 'count'], target: 'item', count: '개 이상' },
  gave_item: { label: '그 인물에게 그 물건을 건넸다', fields: ['target', 'value'], target: 'cast', value: 'item' },
  affection_at_least: { label: '그 인물의 호감도가 그 단계 이상', fields: ['target', 'value'], target: 'cast', value: 'stage' },
  affection_below: { label: '그 인물의 호감도가 그 단계보다 아래', fields: ['target', 'value'], target: 'cast', value: 'stage' },
  day_at_least: { label: '며칠째 이상', fields: ['count'], count: '일째 이상' },
  day_at_most: { label: '며칠째 이하', fields: ['count'], count: '일째 이하' },
  slot_is: { label: '지금 그 시간대', fields: ['target'], target: 'slot' },
  accompanied: { label: '그 인물과 함께 다닌다', fields: ['target'], target: 'cast' },
  event_seen: { label: '그 이벤트가 열린 적이 있다', fields: ['target'], target: 'event' },
};

export const CONDITION_KIND_ORDER = Object.keys(CONDITION_KINDS) as StoryWorldConditionKind[];

export type Choice = { id: string; name: string };
/** 고를 거리. 인물마다 호감도 단계의 이름도 넘긴다 */
export type ConditionChoices = { places: Choice[]; items: Choice[]; cast: (Choice & { stages: string[] })[]; slots: Choice[]; events: Choice[] };

export type ConditionDraft = { kind: StoryWorldConditionKind; target: string; value: string; count: string };
export type ConditionsDraft = { match: StoryWorldConditions['match']; items: ConditionDraft[] };

export const EMPTY_CONDITIONS: ConditionsDraft = { match: 'all', items: [] };

export function conditionsDraft(conditions: StoryWorldConditions | null | undefined): ConditionsDraft {
  if (!conditions) return EMPTY_CONDITIONS;
  return {
    match: conditions.match,
    items: conditions.items.map((item) => ({ kind: item.kind, target: item.target ?? '', value: item.value ?? '', count: String(item.count ?? UNCOUNTED) })),
  };
}

export function addCondition(draft: ConditionsDraft): ConditionsDraft {
  if (draft.items.length >= CONDITIONS_MAX) return draft;
  return { ...draft, items: [...draft.items, { kind: 'reach_place', target: '', value: '', count: '1' }] };
}

/** 조건 하나를 바꾼다. 종류를 바꾸면 대상과 값과 수를 비우고, 호감도·건네기의 인물을 바꾸면 값을 비운다 */
export function changeCondition(draft: ConditionsDraft, index: number, changes: Partial<ConditionDraft>): ConditionsDraft {
  return {
    ...draft,
    items: draft.items.map((item, at) => {
      if (at !== index) return item;
      if (changes.kind && changes.kind !== item.kind) return { kind: changes.kind, target: '', value: '', count: '1' };
      const next = { ...item, ...changes };
      return changes.target !== undefined && changes.target !== item.target && CONDITION_KINDS[item.kind].value === 'stage' ? { ...next, value: '' } : next;
    }),
  };
}

export function removeCondition(draft: ConditionsDraft, index: number): ConditionsDraft {
  return { ...draft, items: draft.items.filter((_, at) => at !== index) };
}

/** 그 종류의 대상으로 고를 거리 */
export function targetChoices(kind: StoryWorldConditionKind, choices: ConditionChoices): Choice[] {
  const target = CONDITION_KINDS[kind].target;
  if (target === 'place') return choices.places;
  if (target === 'item') return choices.items;
  if (target === 'cast') return choices.cast;
  if (target === 'slot') return choices.slots;
  if (target === 'event') return choices.events;
  return [];
}

/** 그 조건의 값으로 고를 거리. 물건이거나, 고른 인물의 호감도 단계 */
export function valueChoices(item: ConditionDraft, choices: ConditionChoices): Choice[] {
  const value = CONDITION_KINDS[item.kind].value;
  if (value === 'item') return choices.items;
  if (value === 'stage') return (choices.cast.find((member) => member.id === item.target)?.stages ?? []).map((stage) => ({ id: stage, name: stage }));
  return [];
}

function countOf(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d{1,3}$/.test(trimmed)) return null;
  const count = Number(trimmed);
  return count >= 1 && count <= CONDITION_COUNT_MAX ? count : null;
}

function conditionHint(item: ConditionDraft, choices: ConditionChoices): string | undefined {
  const spec = CONDITION_KINDS[item.kind];
  if (spec.target) {
    if (item.target === '') return '대상을 골라 주세요.';
    if (!targetChoices(item.kind, choices).some((choice) => choice.id === item.target)) return '없는 대상입니다. 다시 골라 주세요.';
  }
  if (spec.value) {
    if (item.value === '') return spec.value === 'stage' ? '단계를 골라 주세요.' : '물건을 골라 주세요.';
    if (!valueChoices(item, choices).some((choice) => choice.id === item.value)) return '없는 값입니다. 다시 골라 주세요.';
  }
  if (spec.count && countOf(item.count) === null) return `수는 1~${CONDITION_COUNT_MAX} 사이의 정수입니다.`;
  return undefined;
}

/** 조건마다(차례 → 글)의 문제 */
export function conditionsHints(draft: ConditionsDraft, choices: ConditionChoices): Record<number, string> {
  const hints: Record<number, string> = {};
  draft.items.forEach((item, index) => {
    const found = conditionHint(item, choices);
    if (found) hints[index] = found;
  });
  return hints;
}

/** 보낼 모양. 쓰지 않는 칸은 빼고, 수를 쓰지 않으면 1 이다 */
export function toConditions(draft: ConditionsDraft): StoryWorldConditions {
  return {
    match: draft.match,
    items: draft.items.map((item): StoryWorldCondition => {
      const fields = CONDITION_KINDS[item.kind].fields;
      return {
        kind: item.kind,
        ...(fields.includes('target') ? { target: item.target } : {}),
        ...(fields.includes('value') ? { value: item.value } : {}),
        count: fields.includes('count') ? (countOf(item.count) ?? UNCOUNTED) : UNCOUNTED,
      };
    }),
  };
}

/** 조건 한 줄의 글. "공원에 있다", "꽃 2개 이상" 처럼 목록에서 읽힌다 */
export function conditionLabel(kind: StoryWorldConditionKind): string {
  return CONDITION_KINDS[kind].label;
}

type WorldParts = {
  places: Choice[];
  items: Choice[];
  slots: Choice[];
  cast: { id: string; character_id: string; affection: { stages: { name: string }[] } }[];
};

/**
 * 저장된 세계관에서 고를 거리. 인물의 이름은 그 캐릭터의 이름이다(목록에 없으면 빈 이름).
 * 이벤트는 쓰는 쪽이 넘긴다(이벤트 탭은 고치는 중인 이벤트, 엔딩 탭은 저장된 이벤트)
 */
export function savedChoices(world: WorldParts, characters: Choice[], events: Choice[]): ConditionChoices {
  return {
    places: world.places.map((place) => ({ id: place.id, name: place.name })),
    items: world.items.map((item) => ({ id: item.id, name: item.name })),
    slots: world.slots.map((slot) => ({ id: slot.id, name: slot.name })),
    events,
    cast: world.cast.map((member) => ({
      id: member.id,
      name: characters.find((character) => character.id === member.character_id)?.name ?? '',
      stages: member.affection.stages.map((stage) => stage.name),
    })),
  };
}
