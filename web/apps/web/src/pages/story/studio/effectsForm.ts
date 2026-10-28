// web/apps/web/src/pages/story/studio/effectsForm.ts
// 효과 목록(이벤트가 열릴 때, 선택지를 고를 때)의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/worlds/schemas.py 의 Effect).
//
//   - 효과는 종류마다 대상이 다르다(인물, 물건, 장소). 크기(amount)는 호감도(-100~100, 0 아님)와 물건의 수(1~99)만 쓴다
//   - 종류를 바꾸면 대상과 크기를 비운다(대상의 종류가 같으면 대상은 남긴다)
//   - 고를 거리에 없는 대상(그사이 지운 것)은 다시 고르라고 알린다. 목록은 10 개까지

import type { StoryWorldEffect, StoryWorldEffectKind } from '../../../api/storyWorlds';
import type { Choice, ConditionChoices } from './conditionsForm';

export const EFFECTS_MAX = 10;
export const EFFECT_CHANGE_MAX = 100;
export const EFFECT_COUNT_MAX = 99;

type EffectSpec = { label: string; target: 'cast' | 'item' | 'place'; amount?: 'signed' | 'count' };

export const EFFECT_KINDS: Record<StoryWorldEffectKind, EffectSpec> = {
  affection: { label: '인물의 호감도를 바꾼다', target: 'cast', amount: 'signed' },
  give_item: { label: '물건을 준다', target: 'item', amount: 'count' },
  take_item: { label: '물건을 가져간다', target: 'item', amount: 'count' },
  accompany_start: { label: '인물과 함께 다니기 시작한다', target: 'cast' },
  accompany_end: { label: '인물과 함께 다니기를 끝낸다', target: 'cast' },
  move_to: { label: '장소로 옮긴다(시간은 흐르지 않는다)', target: 'place' },
};

export const EFFECT_KIND_ORDER = Object.keys(EFFECT_KINDS) as StoryWorldEffectKind[];

export type EffectDraft = { kind: StoryWorldEffectKind; target: string; amount: string };

export function effectsDraft(effects: StoryWorldEffect[]): EffectDraft[] {
  return effects.map((effect) => ({ kind: effect.kind, target: effect.target, amount: effect.amount === null || effect.amount === undefined ? '' : String(effect.amount) }));
}

export function addEffect(effects: EffectDraft[]): EffectDraft[] {
  return effects.length >= EFFECTS_MAX ? effects : [...effects, { kind: 'affection', target: '', amount: '5' }];
}

/** 효과 하나를 바꾼다. 종류를 바꾸면 크기를 그 종류의 처음 값으로 두고, 대상의 종류가 달라지면 대상을 비운다 */
export function changeEffect(effects: EffectDraft[], index: number, changes: Partial<EffectDraft>): EffectDraft[] {
  return effects.map((effect, at) => {
    if (at !== index) return effect;
    if (changes.kind && changes.kind !== effect.kind) {
      const next = EFFECT_KINDS[changes.kind];
      const target = next.target === EFFECT_KINDS[effect.kind].target ? effect.target : '';
      return { kind: changes.kind, target, amount: next.amount === 'signed' ? '5' : next.amount === 'count' ? '1' : '' };
    }
    return { ...effect, ...changes };
  });
}

export function removeEffect(effects: EffectDraft[], index: number): EffectDraft[] {
  return effects.filter((_, at) => at !== index);
}

export function effectTargets(kind: StoryWorldEffectKind, choices: ConditionChoices): Choice[] {
  const target = EFFECT_KINDS[kind].target;
  if (target === 'cast') return choices.cast;
  if (target === 'item') return choices.items;
  return choices.places;
}

function integer(text: string, min: number, max: number): number | null {
  const trimmed = text.trim();
  if (!/^-?\d{1,3}$/.test(trimmed)) return null;
  const value = Number(trimmed);
  return value >= min && value <= max ? value : null;
}

function effectHint(effect: EffectDraft, choices: ConditionChoices): string | undefined {
  if (effect.target === '') return '대상을 골라 주세요.';
  if (!effectTargets(effect.kind, choices).some((choice) => choice.id === effect.target)) return '없는 대상입니다. 다시 골라 주세요.';
  const amount = EFFECT_KINDS[effect.kind].amount;
  if (amount === 'signed') {
    const value = integer(effect.amount, -EFFECT_CHANGE_MAX, EFFECT_CHANGE_MAX);
    if (value === null) return `크기는 -${EFFECT_CHANGE_MAX}~${EFFECT_CHANGE_MAX} 사이의 정수입니다.`;
    if (value === 0) return '0 은 호감도를 바꾸지 않습니다.';
  }
  if (amount === 'count' && integer(effect.amount, 1, EFFECT_COUNT_MAX) === null) return `수는 1~${EFFECT_COUNT_MAX} 사이의 정수입니다.`;
  return undefined;
}

/** 효과마다(차례 → 글)의 문제 */
export function effectsHints(effects: EffectDraft[], choices: ConditionChoices): Record<number, string> {
  const hints: Record<number, string> = {};
  effects.forEach((effect, index) => {
    const found = effectHint(effect, choices);
    if (found) hints[index] = found;
  });
  return hints;
}

/** 보낼 모양. 크기를 쓰지 않는 종류는 크기를 빼고 보낸다 */
export function toEffects(effects: EffectDraft[]): StoryWorldEffect[] {
  return effects.map((effect) => {
    const amount = EFFECT_KINDS[effect.kind].amount;
    if (!amount) return { kind: effect.kind, target: effect.target };
    return { kind: effect.kind, target: effect.target, amount: amount === 'signed' ? integer(effect.amount, -EFFECT_CHANGE_MAX, EFFECT_CHANGE_MAX) : integer(effect.amount, 1, EFFECT_COUNT_MAX) };
  });
}
