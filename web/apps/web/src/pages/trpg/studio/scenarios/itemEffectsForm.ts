// web/apps/web/src/pages/trpg/studio/scenarios/itemEffectsForm.ts
// 소모품의 효과 목록(#800)과 던지는 판정·치료 보정(#277)의 입력. 순수한 함수다(서버의 ItemRule 검사를 따른다).
//
// - 효과는 5개까지, 적힌 차례대로 낸다. 종류는 회복(heal)·풀기(cure)·피해(damage)·부상(injure)·맞추기(adjust, #804)
// - 회복과 피해는 함께 적지 않는다. 회복·풀기·피해는 한 번씩, 같은 부상을 두 번 입히지 않고 같은 수치를 두 번 맞추지 않는다
// - 맞추기는 룰북의 수치(rules.resources) 하나를 -99~99(0 이 아닌) 만큼 올리거나 내린다. 내리는 것은 해롭다
// - 회복과 피해는 룰북의 양의 등급, 풀기는 룰북의 부상 가운데 결손이 아닌 것(1~5개), 부상은 룰북의 부상 하나
// - 던지는 판정(#801, 장비에도)은 능력치(필수)·난이도(비우면 룰북의 기본). 비우면 룰북의 맞히는 판정으로 던진다

import type { ItemRule, ItemRuleBody, Ruleset } from '../../../../api/types';

export const MAX_EFFECTS = 5;
export const MAX_CURES = 5;

type Effect = ItemRule['effects'][number];
export type EffectKind = Effect['kind'];

export const EFFECT_KINDS: EffectKind[] = ['heal', 'cure', 'damage', 'injure', 'adjust'];
export const EFFECT_LABELS: Record<EffectKind, string> = {
  heal: '회복',
  cure: '부상 풀기',
  damage: '피해',
  injure: '부상 입히기',
  adjust: '수치 맞추기',
};
/** 동료에게는 동료 피해의 설정을 따르는(해로운) 효과. 수치를 내리는 맞추기도 해롭다(서버의 is_drain) */
export const HARMFUL_KINDS: EffectKind[] = ['damage', 'injure'];
const ADJUST_MAX = 99;

/** nature 는 수치를 내리는 맞추기의 성질(#886 ②). 고르는 칸이 아직 없어 받은 대로 지녔다가 보낸다(내리는 것만) */
export type EffectDraft = {
  kind: EffectKind;
  magnitude: string;
  injuries: string[];
  injury: string;
  resource: string;
  amount: string;
  nature?: string | null;
};
export type ThrowDraft = { on: boolean; ability: string; difficulty: string };

export function newEffectDraft(kind: EffectKind = 'heal'): EffectDraft {
  return { kind, magnitude: '', injuries: [], injury: '', resource: '', amount: '' };
}

export function effectDraft(effect: Effect): EffectDraft {
  if (effect.kind === 'cure') return { ...newEffectDraft('cure'), injuries: effect.injuries };
  if (effect.kind === 'injure') return { ...newEffectDraft('injure'), injury: effect.injury };
  if (effect.kind === 'adjust') return { ...newEffectDraft('adjust'), resource: effect.resource, amount: String(effect.amount), nature: effect.nature };
  return { ...newEffectDraft(effect.kind), magnitude: effect.magnitude };
}

export function throwDraft(rule: ItemRule | undefined): ThrowDraft {
  const thrown = rule?.throw;
  return { on: Boolean(thrown), ability: thrown?.ability ?? '', difficulty: thrown?.difficulty ?? '' };
}

/** 효과 하나를 보낼 모양으로. 검사를 통과한 뒤에만 부른다 */
export function toEffect(draft: EffectDraft): Effect {
  if (draft.kind === 'cure') return { kind: 'cure', injuries: draft.injuries };
  if (draft.kind === 'injure') return { kind: 'injure', injury: draft.injury };
  if (draft.kind === 'adjust') return toAdjust(draft);
  return { kind: draft.kind, magnitude: draft.magnitude };
}

/** 맞추기 하나. 받은 성질(#886 ②)은 내리는 것(음수)일 때만 붙인다. 올리는 것에 성질을 달면 서버가 받지 않는다 */
function toAdjust(draft: EffectDraft): Effect {
  const amount = Number(draft.amount.trim());
  return draft.nature && amount < 0 ? { kind: 'adjust', resource: draft.resource, amount, nature: draft.nature } : { kind: 'adjust', resource: draft.resource, amount };
}

/** 맞추는 양의 글을 정수로. -99~99 의 0 이 아닌 정수가 아니면 null */
export function adjustAmount(value: string): number | null {
  if (!/^-?\d+$/.test(value.trim())) return null;
  const amount = Number(value.trim());
  return amount !== 0 && Math.abs(amount) <= ADJUST_MAX ? amount : null;
}

export function toThrow(draft: ThrowDraft): ItemRuleBody['throw'] {
  if (!draft.on) return null;
  return { ability: draft.ability, difficulty: draft.difficulty === '' ? null : draft.difficulty };
}

/** 풀 수 있는 부상(짧은 것과 오래 가는 것). 결손은 풀지 못한다 */
export function curableInjuries(rules: Ruleset | null): Ruleset['injuries'] {
  return (rules?.injuries ?? []).filter((injury) => injury.healing !== 'permanent');
}

/** 부상 하나를 풀기에 넣거나 뺀다. 룰북의 부상 차례를 지킨다 */
export function toggleCure(injuries: string[], key: string, rules: Ruleset | null): string[] {
  const next = injuries.includes(key) ? injuries.filter((one) => one !== key) : [...injuries, key];
  const order = (rules?.injuries ?? []).map((injury) => injury.key);
  return [...order.filter((one) => next.includes(one)), ...next.filter((one) => !order.includes(one))];
}

function effectHint(draft: EffectDraft): string | null {
  if ((draft.kind === 'heal' || draft.kind === 'damage') && draft.magnitude === '') return '양을 고르세요.';
  if (draft.kind === 'cure' && draft.injuries.length === 0) return '풀 부상을 하나 이상 고르세요.';
  if (draft.kind === 'cure' && draft.injuries.length > MAX_CURES) return `풀 부상은 ${MAX_CURES}개까지입니다.`;
  if (draft.kind === 'injure' && draft.injury === '') return '입힐 부상을 고르세요.';
  if (draft.kind === 'adjust' && draft.resource === '') return '맞출 수치를 고르세요.';
  if (draft.kind === 'adjust' && adjustAmount(draft.amount) === null) return `양은 -${ADJUST_MAX}~${ADJUST_MAX} 사이의 0 이 아닌 정수입니다.`;
  return null;
}

/** 효과 목록 전체의 문제. 없으면 null */
function listHint(effects: EffectDraft[]): string | null {
  const kinds = effects.map((one) => one.kind);
  if (effects.length > MAX_EFFECTS) return `효과는 ${MAX_EFFECTS}개까지입니다.`;
  if (kinds.includes('heal') && kinds.includes('damage')) return '회복과 피해는 한 물건에 함께 적지 않습니다.';
  if ((['heal', 'cure', 'damage'] as EffectKind[]).some((kind) => kinds.filter((one) => one === kind).length > 1)) return '회복, 풀기, 피해는 한 번씩만 적습니다.';
  const injured = effects.filter((one) => one.kind === 'injure' && one.injury !== '').map((one) => one.injury);
  if (new Set(injured).size !== injured.length) return '같은 부상을 두 번 입힙니다.';
  const adjusted = effects.filter((one) => one.kind === 'adjust' && one.resource !== '').map((one) => one.resource);
  if (new Set(adjusted).size !== adjusted.length) return '같은 수치를 두 번 맞춥니다.';
  return null;
}

/** 던지는 판정의 문제. 켰으면 능력치를 골라야 한다. 없으면 null */
export function throwHint(thrown: ThrowDraft): string | null {
  return thrown.on && thrown.ability === '' ? '던지는 판정의 능력치를 고르세요.' : null;
}

/** 소모품의 칸에서 보내기 전에 알릴 것. "effect.<차례>", "effects" → 글 */
export function effectHints(effects: EffectDraft[]): Record<string, string> {
  const hints: Record<string, string> = {};
  effects.forEach((one, index) => {
    const hint = effectHint(one);
    if (hint) hints[`effect.${index}`] = hint;
  });
  const list = listHint(effects);
  if (list) hints.effects = list;
  return hints;
}

function magnitudeName(rules: Ruleset | null, key: string): string {
  return rules?.magnitudes.find((one) => one.key === key)?.name ?? key;
}

function injuryName(rules: Ruleset | null, key: string): string {
  return rules?.injuries.find((one) => one.key === key)?.name ?? key;
}

function resourceName(rules: Ruleset | null, key: string): string {
  return rules?.resources.find((one) => one.key === key)?.name ?? key;
}

/** 맞추기의 글. "마나 +3", "마나 -2" */
export function adjustLine(name: string, amount: number): string {
  return `${name} ${amount > 0 ? '+' : ''}${amount}`;
}

/** 효과 하나의 글. "회복 가벼움", "풀기: 중독, 기절", "피해 보통", "부상: 기절" */
export function effectLine(effect: Effect, rules: Ruleset | null): string {
  if (effect.kind === 'heal') return `회복 ${magnitudeName(rules, effect.magnitude)}`;
  if (effect.kind === 'damage') return `피해 ${magnitudeName(rules, effect.magnitude)}`;
  if (effect.kind === 'cure') return `풀기: ${effect.injuries.map((key) => injuryName(rules, key)).join(', ')}`;
  if (effect.kind === 'adjust') return adjustLine(resourceName(rules, effect.resource), effect.amount);
  return `부상: ${injuryName(rules, effect.injury)}`;
}
