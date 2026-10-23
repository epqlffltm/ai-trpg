// web/apps/web/src/pages/chat/studio/characters/affectionForm.ts
// 캐릭터의 호감도 탭의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/characters/schemas.py 의 Affection).
//
//   - 호감도는 값 하나(0~100)와 단계들이다. 쓰지 않으면 null 로 보낸다
//   - 단계: 1~10 개. 첫 단계는 0 에서 시작하고 경계는 차례로 커진다. 이름(20자)은 겹치지 않는다
//   - 규칙: 50 개까지. 사용자가 물건을 건네거나(give_item) 쓰거나(use_item) 장소에 가면(reach_place) -20~20(0 은 아님)만큼 바꾼다.
//     once 면 처음 한 번만. id 는 화면이 붙인다(chat 이 "이미 했다"를 이 id 로 적으므로 바뀌면 안 된다)
//   - 모델의 한 번(model_step): 모델이 답 하나에 바꿀 수 있는 크기(0~20). 0 이면 규칙만 바꾼다
// 숫자 칸은 글로 들고 있다가 보낼 때 바꾼다.

import type {
  AssetAffection,
  AssetAffectionDisplay,
  AssetCharacterDetail,
  AssetCharacterUpdate,
  AssetTriggerKind,
} from '../../../../api/types';

export const AFFECTION_MAX = 100;
export const STAGES_MAX = 10;
export const STAGE_NAME_MAX = 20;
export const RULES_MAX = 50;
export const CHANGE_MAX = 20;
export const MODEL_STEP_DEFAULT = 3;

export type StageDraft = { name: string; at: string };
export type RuleDraft = { id: string; kind: AssetTriggerKind; target: string; change: string; once: boolean };

export type AffectionDraft = {
  enabled: boolean;
  display: AssetAffectionDisplay;
  start: string;
  modelStep: string;
  stages: StageDraft[];
  rules: RuleDraft[];
};

/** 켤 때의 처음 모양. 단계 하나(0 에서 시작) */
export function newAffectionDraft(): AffectionDraft {
  return { enabled: true, display: 'number', start: '0', modelStep: String(MODEL_STEP_DEFAULT), stages: [{ name: '처음', at: '0' }], rules: [] };
}

export function affectionDraft(character: AssetCharacterDetail): AffectionDraft {
  const affection = character.affection;
  if (!affection) return { ...newAffectionDraft(), enabled: false };
  return {
    enabled: true,
    display: affection.display ?? 'number',
    start: String(affection.start ?? 0),
    modelStep: String(affection.model_step ?? MODEL_STEP_DEFAULT),
    stages: affection.stages.map((stage) => ({ name: stage.name, at: String(stage.at) })),
    rules: (affection.rules ?? []).map((rule) => ({
      id: rule.id,
      kind: rule.on.kind,
      target: rule.on.target,
      change: String(rule.change),
      once: rule.once ?? false,
    })),
  };
}

/** text 가 min~max 의 정수면 그 수, 아니면 null. 음수도 받는다 */
export function integerIn(text: string, min: number, max: number): number | null {
  const trimmed = text.trim();
  if (!/^-?\d{1,3}$/.test(trimmed)) return null;
  const value = Number(trimmed);
  return value >= min && value <= max ? value : null;
}

/** 단계를 더한다. 경계는 마지막 단계보다 10 크게(넘치면 100) 제안한다 */
export function addStage(draft: AffectionDraft): AffectionDraft {
  if (draft.stages.length >= STAGES_MAX) return draft;
  const last = integerIn(draft.stages.at(-1)?.at ?? '0', 0, AFFECTION_MAX) ?? 0;
  return { ...draft, stages: [...draft.stages, { name: '', at: String(Math.min(last + 10, AFFECTION_MAX)) }] };
}

export function changeStage(draft: AffectionDraft, index: number, changes: Partial<StageDraft>): AffectionDraft {
  return { ...draft, stages: draft.stages.map((stage, at) => (at === index ? { ...stage, ...changes } : stage)) };
}

/** 단계를 지운다. 하나는 남긴다 */
export function removeStage(draft: AffectionDraft, index: number): AffectionDraft {
  if (draft.stages.length <= 1) return draft;
  return { ...draft, stages: draft.stages.filter((_, at) => at !== index) };
}

export function addRule(draft: AffectionDraft, id: string): AffectionDraft {
  if (draft.rules.length >= RULES_MAX) return draft;
  return { ...draft, rules: [...draft.rules, { id, kind: 'give_item', target: '', change: '5', once: false }] };
}

/** 규칙을 바꾼다. 행동의 종류가 바뀌면(물건 ↔ 장소) 대상을 비운다 */
export function changeRule(draft: AffectionDraft, id: string, changes: Partial<Omit<RuleDraft, 'id'>>): AffectionDraft {
  return {
    ...draft,
    rules: draft.rules.map((rule) => {
      if (rule.id !== id) return rule;
      const next = { ...rule, ...changes };
      return changes.kind && targetsPlace(changes.kind) !== targetsPlace(rule.kind) ? { ...next, target: '' } : next;
    }),
  };
}

export function removeRule(draft: AffectionDraft, id: string): AffectionDraft {
  return { ...draft, rules: draft.rules.filter((rule) => rule.id !== id) };
}

/** 그 행동의 대상이 장소인가(아니면 물건) */
export function targetsPlace(kind: AssetTriggerKind): boolean {
  return kind === 'reach_place';
}

function stageHints(stages: StageDraft[]): Record<number, string> {
  const hints: Record<number, string> = {};
  const seen = new Set<string>();
  let previous = -1;
  stages.forEach((stage, index) => {
    const name = stage.name.trim();
    const at = integerIn(stage.at, 0, AFFECTION_MAX);
    if (name === '') hints[index] = '이름을 적어 주세요.';
    else if (name.length > STAGE_NAME_MAX) hints[index] = `이름은 ${STAGE_NAME_MAX}자까지입니다.`;
    else if (seen.has(name)) hints[index] = '같은 이름의 단계가 이미 있습니다.';
    else if (at === null) hints[index] = `경계는 0~${AFFECTION_MAX} 사이의 정수입니다.`;
    else if (index === 0 && at !== 0) hints[index] = '첫 단계는 0 에서 시작합니다.';
    else if (index > 0 && at <= previous) hints[index] = '경계는 위의 단계보다 커야 합니다.';
    seen.add(name);
    if (at !== null) previous = at;
  });
  return hints;
}

function ruleHint(rule: RuleDraft): string | undefined {
  if (rule.target === '') return targetsPlace(rule.kind) ? '장소를 골라 주세요.' : '물건을 골라 주세요.';
  const change = integerIn(rule.change, -CHANGE_MAX, CHANGE_MAX);
  if (change === null) return `변화는 -${CHANGE_MAX}~${CHANGE_MAX} 사이의 정수입니다.`;
  if (change === 0) return '0 은 호감도를 바꾸지 않습니다.';
  return undefined;
}

export type AffectionHints = { start?: string; modelStep?: string; stages: Record<number, string>; rules: Record<string, string> };

/** 칸마다의 문제. 쓰지 않으면 문제가 없다 */
export function affectionHints(draft: AffectionDraft): AffectionHints {
  if (!draft.enabled) return { stages: {}, rules: {} };
  const hints: AffectionHints = { stages: stageHints(draft.stages), rules: {} };
  if (integerIn(draft.start, 0, AFFECTION_MAX) === null) hints.start = `처음 값은 0~${AFFECTION_MAX} 사이의 정수입니다.`;
  if (integerIn(draft.modelStep, 0, CHANGE_MAX) === null) hints.modelStep = `0~${CHANGE_MAX} 사이의 정수입니다.`;
  for (const rule of draft.rules) {
    const found = ruleHint(rule);
    if (found) hints.rules[rule.id] = found;
  }
  return hints;
}

export function hasAffectionHints(hints: AffectionHints): boolean {
  return Boolean(hints.start || hints.modelStep) || Object.keys(hints.stages).length > 0 || Object.keys(hints.rules).length > 0;
}

/** 호감도 탭의 칸만 보낸다. 힌트가 없을 때만 부른다. 쓰지 않으면 null */
export function toAffectionBody(draft: AffectionDraft): AssetCharacterUpdate {
  if (!draft.enabled) return { affection: null };
  const affection: AssetAffection = {
    display: draft.display,
    start: integerIn(draft.start, 0, AFFECTION_MAX) ?? 0,
    model_step: integerIn(draft.modelStep, 0, CHANGE_MAX) ?? MODEL_STEP_DEFAULT,
    stages: draft.stages.map((stage) => ({ name: stage.name.trim(), at: integerIn(stage.at, 0, AFFECTION_MAX) ?? 0 })),
    rules: draft.rules.map((rule) => ({
      id: rule.id,
      on: { kind: rule.kind, target: rule.target },
      change: integerIn(rule.change, -CHANGE_MAX, CHANGE_MAX) ?? 0,
      once: rule.once,
    })),
  };
  return { affection };
}
