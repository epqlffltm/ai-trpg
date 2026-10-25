// web/apps/web/src/pages/trpg/studio/scenarios/itemEffectsForm.ts
// 소모품의 효과 목록(#800)과 던지는 판정·치료 보정(#277)의 입력. 순수한 함수다(서버의 ItemRule 검사를 따른다).
//
// - 효과는 5개까지, 적힌 차례대로 낸다. 종류는 회복(heal)·풀기(cure)·피해(damage)·부상(injure)
// - 회복과 피해는 함께 적지 않는다. 회복·풀기·피해는 한 번씩, 같은 부상을 두 번 입히지 않는다
// - 회복과 피해는 룰북의 양의 등급, 풀기는 룰북의 부상 가운데 결손이 아닌 것(1~5개), 부상은 룰북의 부상 하나
// - 던지는 판정은 능력치(필수)·난이도(비우면 룰북의 기본)·맞으면 다치는 양(필수). 치료 보정은 1~10

import type { ItemRule, ItemRuleBody, Ruleset } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';

export const MAX_EFFECTS = 5;
export const MAX_CURES = 5;
export const TREAT_BONUS_MAX = 10;

type Effect = ItemRule['effects'][number];
export type EffectKind = Effect['kind'];

export const EFFECT_KINDS: EffectKind[] = ['heal', 'cure', 'damage', 'injure'];
export const EFFECT_LABELS: Record<EffectKind, string> = { heal: '회복', cure: '부상 풀기', damage: '피해', injure: '부상 입히기' };
/** 동료에게 쓸 수 없는(해로운) 효과 */
export const HARMFUL_KINDS: EffectKind[] = ['damage', 'injure'];

export type EffectDraft = { kind: EffectKind; magnitude: string; injuries: string[]; injury: string };
export type ThrowDraft = { on: boolean; ability: string; difficulty: string; harm: string };

export function newEffectDraft(kind: EffectKind = 'heal'): EffectDraft {
  return { kind, magnitude: '', injuries: [], injury: '' };
}

export function effectDraft(effect: Effect): EffectDraft {
  if (effect.kind === 'cure') return { ...newEffectDraft('cure'), injuries: effect.injuries };
  if (effect.kind === 'injure') return { ...newEffectDraft('injure'), injury: effect.injury };
  return { ...newEffectDraft(effect.kind), magnitude: effect.magnitude };
}

export function throwDraft(rule: ItemRule | undefined): ThrowDraft {
  const thrown = rule?.throw;
  return { on: Boolean(thrown), ability: thrown?.ability ?? '', difficulty: thrown?.difficulty ?? '', harm: thrown?.harm ?? '' };
}

/** 효과 하나를 보낼 모양으로. 검사를 통과한 뒤에만 부른다 */
export function toEffect(draft: EffectDraft): Effect {
  if (draft.kind === 'cure') return { kind: 'cure', injuries: draft.injuries };
  if (draft.kind === 'injure') return { kind: 'injure', injury: draft.injury };
  return { kind: draft.kind, magnitude: draft.magnitude };
}

export function toThrow(draft: ThrowDraft): ItemRuleBody['throw'] {
  if (!draft.on) return null;
  return { ability: draft.ability, difficulty: draft.difficulty === '' ? null : draft.difficulty, harm: draft.harm };
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
  return null;
}

/** 보내기 전에 알릴 것. "effect.<차례>", "effects", "throw", "treat_bonus" → 글 */
export function effectHints(effects: EffectDraft[], thrown: ThrowDraft, treatBonus: string): Record<string, string> {
  const hints: Record<string, string> = {};
  effects.forEach((one, index) => {
    const hint = effectHint(one);
    if (hint) hints[`effect.${index}`] = hint;
  });
  const list = listHint(effects);
  if (list) hints.effects = list;
  if (thrown.on && (thrown.ability === '' || thrown.harm === '')) hints.throw = '던지는 판정의 능력치와 맞으면 다치는 양을 고르세요.';
  if (treatBonus.trim() !== '' && wholeNumber(treatBonus, 1, TREAT_BONUS_MAX) === null) hints.treat_bonus = `1~${TREAT_BONUS_MAX} 사이의 정수입니다.`;
  return hints;
}

function magnitudeName(rules: Ruleset | null, key: string): string {
  return rules?.magnitudes.find((one) => one.key === key)?.name ?? key;
}

function injuryName(rules: Ruleset | null, key: string): string {
  return rules?.injuries.find((one) => one.key === key)?.name ?? key;
}

/** 효과 하나의 글. "회복 가벼움", "풀기: 중독, 기절", "피해 보통", "부상: 기절" */
export function effectLine(effect: Effect, rules: Ruleset | null): string {
  if (effect.kind === 'heal') return `회복 ${magnitudeName(rules, effect.magnitude)}`;
  if (effect.kind === 'damage') return `피해 ${magnitudeName(rules, effect.magnitude)}`;
  if (effect.kind === 'cure') return `풀기: ${effect.injuries.map((key) => injuryName(rules, key)).join(', ')}`;
  return `부상: ${injuryName(rules, effect.injury)}`;
}
