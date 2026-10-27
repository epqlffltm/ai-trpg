// web/apps/web/src/pages/trpg/studio/rulebooks/resourcesForm.ts
// 룰북의 수치(#804, rules.resources)의 입력. 마나, 스태미나, 광기 같은 것이다. 순수한 함수다(서버의 Resource,
// trpg-server/app/engine/ruleset.py 를 따른다).
//
// - 이름표(영어 소문자로 시작, 소문자·숫자·밑줄, 20자), 보이는 이름(30자). 이름표는 겹치지 않는다. 6개까지
// - 최소(0~999, 비우면 0), 최대 = 기준값(0~999) + 능력치의 보정(고르지 않으면 고정값), 상한(1~999, 비우면 없음)
// - 고정값이나 상한은 최소보다 커야 한다(서버가 거절한다)
// - 시작: 가득(max) 또는 비운 채(min)
// - 짧은 휴식과 긴 휴식마다: 바꾸지 않음, 올리기·내리기(양 1~999), 채우기, 비우기
// 숫자 칸은 고치는 동안 글로 둔다. 보낼 때 정수로 바꾼다.
// 라운드마다의 변화와 문턱(each_round, at_min, at_max), 보이기(visibility), 가진 쪽(holders)은 아직 고치는 칸이 없다.
// 받은 값을 그대로 지녔다가 보낸다(저장할 때 지워지지 않게). 새 수치는 없음, 모두, 캐릭터만이다.

import type { Resource, ResourceShift } from '../../../../api/types';

type ShiftKind = ResourceShift['kind'];
/** 고치는 칸이 아직 없어 받은 대로 지녔다가 보내는 것 */
type KeptFields = Pick<Resource, 'each_round' | 'at_min' | 'at_max' | 'visibility' | 'holders'>;
type StartKind = Resource['start'];

export const RESOURCES_MAX = 6;
const NEW_KEPT: KeptFields = { each_round: null, at_min: null, at_max: null, visibility: 'everyone', holders: ['characters'] };
const VALUE_MAX = 999;
const KEY_PATTERN = /^[a-z][a-z0-9_]{0,19}$/;
const NAME_MAX = 30;

export const SHIFT_KINDS: ShiftKind[] = ['raise', 'lower', 'fill', 'empty'];
export const SHIFT_LABELS: Record<ShiftKind | '', string> = { '': '바꾸지 않음', raise: '올리기', lower: '내리기', fill: '채우기', empty: '비우기' };
export const START_LABELS: Record<StartKind, string> = { max: '가득', min: '비운 채' };

export type ShiftDraft = { kind: ShiftKind | ''; amount: string };

export type ResourceDraft = {
  key: string;
  name: string;
  min: string;
  base: string;
  /** 최대에 보정을 더하는 능력치. 빈 글이면 고정값 */
  ability: string;
  cap: string;
  start: StartKind;
  short: ShiftDraft;
  long: ShiftDraft;
  kept: KeptFields;
};

/** 칸의 글을 정수로. 정수가 아니거나 범위 밖이면 null(rulebookForm.ts 의 것과 같다. 서로 가져오지 않게 둔다) */
function wholeNumber(value: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const number = Number(value.trim());
  return number >= min && number <= max ? number : null;
}

function shiftDraft(shift: ResourceShift | null | undefined): ShiftDraft {
  return shift ? { kind: shift.kind, amount: shift.amount == null ? '' : String(shift.amount) } : { kind: '', amount: '' };
}

/** 서버의 수치를 고칠 거리로 */
export function resourceDraft(resource: Resource): ResourceDraft {
  return {
    key: resource.key,
    name: resource.name,
    min: resource.min ? String(resource.min) : '',
    base: String(resource.max.base),
    ability: resource.max.ability ?? '',
    cap: resource.max.cap == null ? '' : String(resource.max.cap),
    start: resource.start,
    short: shiftDraft(resource.rest.short),
    long: shiftDraft(resource.rest.long),
    kept: { each_round: resource.each_round ?? null, at_min: resource.at_min ?? null, at_max: resource.at_max ?? null, visibility: resource.visibility, holders: resource.holders },
  };
}

/** 새 수치 한 줄. 아직 쓰지 않은 이름표(resource, resource_2 …), 고정값 5, 가득에서 시작, 긴 휴식에 채운다 */
export function newResourceDraft(drafts: ResourceDraft[]): ResourceDraft {
  const taken = new Set(drafts.map((draft) => draft.key));
  let key = 'resource';
  for (let number = 2; taken.has(key); number += 1) key = `resource_${number}`;
  return { key, name: '', min: '', base: '5', ability: '', cap: '', start: 'max', short: { kind: '', amount: '' }, long: { kind: 'fill', amount: '' }, kept: NEW_KEPT };
}

function stepping(kind: ShiftKind | ''): boolean {
  return kind === 'raise' || kind === 'lower';
}

function toShift(draft: ShiftDraft): ResourceShift | null {
  if (draft.kind === '') return null;
  if (!stepping(draft.kind)) return { kind: draft.kind, amount: null };
  return { kind: draft.kind, amount: wholeNumber(draft.amount, 1, VALUE_MAX) };
}

/** 보낼 모양. 검사(resourceHints)를 지난 뒤에 부른다 */
export function toResource(draft: ResourceDraft): Resource {
  const cap = draft.cap.trim() === '' ? null : wholeNumber(draft.cap, 1, VALUE_MAX);
  return {
    key: draft.key.trim(),
    name: draft.name.trim(),
    min: draft.min.trim() === '' ? 0 : (wholeNumber(draft.min, 0, VALUE_MAX) ?? 0),
    max: { base: wholeNumber(draft.base, 0, VALUE_MAX) ?? 0, ability: draft.ability || null, cap },
    start: draft.start,
    rest: { short: toShift(draft.short), long: toShift(draft.long) },
    ...draft.kept,
  };
}

function rowHints(draft: ResourceDraft, index: number): Record<string, string> {
  const hints: Record<string, string> = {};
  const at = (field: string) => `resource.${index}.${field}`;
  if (!KEY_PATTERN.test(draft.key.trim())) hints[at('key')] = '이름표는 영어 소문자로 시작하고 소문자·숫자·밑줄로 20자까지입니다.';
  const name = draft.name.trim();
  if (name === '' || name.length > NAME_MAX) hints[at('name')] = `이름을 ${NAME_MAX}자까지 적어 주세요.`;
  const min = draft.min.trim() === '' ? 0 : wholeNumber(draft.min, 0, VALUE_MAX);
  if (min === null) hints[at('min')] = `최소는 0~${VALUE_MAX} 사이의 정수입니다.`;
  const base = wholeNumber(draft.base, 0, VALUE_MAX);
  if (base === null) hints[at('base')] = `기준값은 0~${VALUE_MAX} 사이의 정수입니다.`;
  const cap = draft.cap.trim() === '' ? undefined : wholeNumber(draft.cap, 1, VALUE_MAX);
  if (cap === null) hints[at('cap')] = `상한은 1~${VALUE_MAX} 사이의 정수입니다.`;
  const ceiling = cap ?? (draft.ability ? undefined : base);
  if (min !== null && ceiling != null && ceiling <= min) hints[at('base')] = '최대(고정값이나 상한)가 최소보다 커야 합니다.';
  for (const length of ['short', 'long'] as const) {
    const shift = draft[length];
    if (stepping(shift.kind) && wholeNumber(shift.amount, 1, VALUE_MAX) === null) hints[at(length)] = `양은 1~${VALUE_MAX} 사이의 정수입니다.`;
  }
  return hints;
}

/** 보내기 전에 알릴 것. "resource.<차례>.<칸>", "resources" → 글. 비었으면 보낼 수 있다 */
export function resourceHints(drafts: ResourceDraft[]): Record<string, string> {
  const hints = Object.assign({}, ...drafts.map(rowHints)) as Record<string, string>;
  const keys = drafts.map((draft) => draft.key.trim());
  if (new Set(keys).size !== keys.length) hints.resources = '같은 이름표의 수치가 두 번 있습니다.';
  if (drafts.length > RESOURCES_MAX) hints.resources = `수치는 ${RESOURCES_MAX}개까지입니다.`;
  return hints;
}

/** 수치 한 줄의 글. "마나 0~(3 + 마음, 10 까지) · 가득에서 시작 · 짧은 휴식 +2 · 긴 휴식 채우기" */
export function resourceLine(resource: Resource, abilityName: (key: string) => string): string {
  const max = resource.max.ability ? `${resource.max.base} + ${abilityName(resource.max.ability)}` : String(resource.max.base);
  const cap = resource.max.cap != null ? `, ${resource.max.cap} 까지` : '';
  const parts = [`${resource.name} ${resource.min}~(${max}${cap})`, `${START_LABELS[resource.start]}에서 시작`];
  if (resource.rest.short) parts.push(`짧은 휴식 ${shiftLabel(resource.rest.short)}`);
  if (resource.rest.long) parts.push(`긴 휴식 ${shiftLabel(resource.rest.long)}`);
  return parts.join(' · ');
}

function shiftLabel(shift: ResourceShift): string {
  if (shift.kind === 'raise') return `+${shift.amount}`;
  if (shift.kind === 'lower') return `-${shift.amount}`;
  return SHIFT_LABELS[shift.kind];
}
