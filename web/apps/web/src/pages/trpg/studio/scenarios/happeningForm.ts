// web/apps/web/src/pages/trpg/studio/scenarios/happeningForm.ts
// 사건 규칙 하나의 입력과 사건 규칙 목록을 바꾸는 것(B9 퀘스트·사건 탭, #367). 순수한 함수다.
// 사건 규칙은 붙인 로어북의 사건 항목 하나다. 조건(1~5, 퀘스트의 것과 같다, 가져가기 없음)이 채워지면 한 번 일어나 효과(1~5)를 낸다.
// 효과: 캐릭터 옮기기(모두, 또는 한 장소에 선 사람), 인물 옮기기, 길의 문 잠그기·열기(장치 하나 또는 모두), 부서진 문 고치기.
// 문의 효과는 판의 길(두 끝)을 가리킨다. 그 길에 문이 있는지는 게시 점검이 본다(happening_route_invalid).

import type { DoorDevice, HappeningEffect, HappeningEffectBody, HappeningRule, HappeningRuleBody, QuestMatch } from '../../../../api/types';
import { conditionDrafts, conditionsHints, conditionLine, toConditions, type ConditionDraft, type Targets } from './conditionsForm';

export const MAX_HAPPENINGS = 50;
export const MAX_EFFECTS = 5;

export type EffectKind = HappeningEffect['kind'];

const EFFECT_LABELS: Record<EffectKind, string> = {
  move: '캐릭터를 옮긴다',
  move_npc: '인물을 옮긴다',
  lock_route: '길의 문을 잠근다',
  unlock_route: '길의 문을 연다',
  repair_route: '부서진 문을 고친다',
};

export const EFFECT_KINDS = Object.keys(EFFECT_LABELS) as EffectKind[];

export function effectKindLabel(kind: EffectKind): string {
  return EFFECT_LABELS[kind];
}

/** 효과 하나의 입력. 길은 "from|to"(판의 길의 두 끝), 장치는 '' 이면 그 문의 장치 모두 */
export type EffectDraft = { kind: EffectKind; toPlace: string; fromPlace: string; npc: string; route: string; device: '' | DoorDevice };

export function routeKey(from: string, to: string): string {
  return `${from}|${to}`;
}

function effectDraft(effect: HappeningEffect): EffectDraft {
  const blank: EffectDraft = { kind: effect.kind, toPlace: '', fromPlace: '', npc: '', route: '', device: '' };
  if (effect.kind === 'move') return { ...blank, toPlace: effect.to_place ?? '', fromPlace: effect.from_place ?? '' };
  if (effect.kind === 'move_npc') return { ...blank, npc: effect.npc, toPlace: effect.to_place };
  if (effect.kind === 'repair_route') return { ...blank, route: routeKey(effect.from_place, effect.to_place) };
  return { ...blank, route: routeKey(effect.from_place, effect.to_place), device: effect.device ?? '' };
}

export function newEffect(): EffectDraft {
  return { kind: 'move', toPlace: '', fromPlace: '', npc: '', route: '', device: '' };
}

export type HappeningDraft = { when: ConditionDraft[]; match: QuestMatch; effects: EffectDraft[] };

export function happeningDraft(rule: HappeningRule | undefined): HappeningDraft {
  return { when: conditionDrafts(rule?.when ?? []), match: rule?.match ?? 'all', effects: (rule?.effects ?? []).map(effectDraft) };
}

export type HappeningHints = { when: Record<number, string>; effects: Record<number, string>; fields: Record<string, string> };

function effectHint(effect: EffectDraft): string | null {
  if (effect.kind === 'move') {
    if (effect.toPlace === '') return '옮겨 갈 장소를 골라 주세요.';
    if (effect.fromPlace === effect.toPlace) return '옮기는 곳과 옮겨지는 사람이 선 곳이 같습니다.';
  }
  if (effect.kind === 'move_npc' && (effect.npc === '' || effect.toPlace === '')) return '옮길 인물과 장소를 골라 주세요.';
  if ((effect.kind === 'lock_route' || effect.kind === 'unlock_route' || effect.kind === 'repair_route') && effect.route === '') return '길을 골라 주세요.';
  return null;
}

export function happeningHints(draft: HappeningDraft, entryId: string): HappeningHints {
  const fields: Record<string, string> = {};
  if (draft.when.length === 0) fields.when = '일어나는 조건을 하나는 적어 주세요.';
  if (draft.effects.length === 0) fields.effects = '효과를 하나는 적어 주세요.';
  const effects: Record<number, string> = {};
  draft.effects.forEach((effect, index) => {
    const hint = effectHint(effect);
    if (hint) effects[index] = hint;
  });
  return { when: conditionsHints(draft.when, entryId), effects, fields };
}

export function hasHappeningHints(hints: HappeningHints): boolean {
  return [hints.when, hints.effects, hints.fields].some((part) => Object.keys(part).length > 0);
}

function toEffect(effect: EffectDraft): HappeningEffectBody {
  const [from = '', to = ''] = effect.route.split('|');
  switch (effect.kind) {
    case 'move':
      return { kind: 'move', to_place: effect.toPlace, from_place: effect.fromPlace || null };
    case 'move_npc':
      return { kind: 'move_npc', npc: effect.npc, to_place: effect.toPlace };
    case 'repair_route':
      return { kind: 'repair_route', from_place: from, to_place: to };
    default:
      return { kind: effect.kind, from_place: from, to_place: to, device: effect.device || null };
  }
}

/** 보낼 규칙. 사건은 물건을 가져가지 않는다 */
export function toHappening(entryId: string, draft: HappeningDraft): HappeningRuleBody {
  return { entry_id: entryId, when: toConditions(draft.when, false), match: draft.match, effects: draft.effects.map(toEffect) };
}

/** 받은 규칙을 보낼 모양으로(받은 쪽은 옮기는 곳이 비어 있을 수 있다고 적혀 있다) */
function asBody(rule: HappeningRule): HappeningRuleBody {
  return toHappening(rule.entry_id, happeningDraft(rule));
}

export function withHappening(rules: HappeningRule[], rule: HappeningRuleBody): HappeningRuleBody[] {
  const bodies = rules.map(asBody);
  return bodies.some((one) => one.entry_id === rule.entry_id) ? bodies.map((one) => (one.entry_id === rule.entry_id ? rule : one)) : [...bodies, rule];
}

export function withoutHappening(rules: HappeningRule[], entryId: string): HappeningRuleBody[] {
  return rules.filter((one) => one.entry_id !== entryId).map(asBody);
}

/** 효과 한 줄. "모두 → 종탑", "수도원 문의 사람 → 종탑", "문지기 → 지하 묘지", "수도원 문–종탑의 자물쇠 잠금" */
export function effectLine(effect: HappeningEffect, targets: Targets): string {
  const place = (id: string) => targets.places.find((one) => one.id === id)?.name ?? '(찾을 수 없음)';
  const device = (value: DoorDevice | null | undefined) => (value === 'lock' ? '자물쇠' : value === 'bar' ? '빗장' : '문');
  switch (effect.kind) {
    case 'move':
      return effect.from_place ? `${place(effect.from_place)}의 사람 → ${place(effect.to_place ?? '')}` : `모두 → ${place(effect.to_place ?? '')}`;
    case 'move_npc':
      return `${targets.npcs.find((one) => one.id === effect.npc)?.name ?? '(찾을 수 없음)'} → ${place(effect.to_place)}`;
    case 'lock_route':
      return `${place(effect.from_place)}–${place(effect.to_place)}의 ${device(effect.device)} 잠금`;
    case 'unlock_route':
      return `${place(effect.from_place)}–${place(effect.to_place)}의 ${device(effect.device)} 열림`;
    case 'repair_route':
      return `${place(effect.from_place)}–${place(effect.to_place)}의 문 고침`;
  }
}

/** 목록의 한 줄. "종탑에 닿는다 ⇒ 모두 → 지하 묘지" */
export function happeningLine(rule: HappeningRule, targets: Targets): string {
  const when = rule.when.map((one) => conditionLine(one, targets)).join(rule.match === 'all' ? ' 그리고 ' : ' 또는 ');
  return `${when} ⇒ ${rule.effects.map((one) => effectLine(one, targets)).join(', ')}`;
}
