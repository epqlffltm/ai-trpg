// web/apps/web/src/pages/trpg/room/round/roundView.ts
// 라운드를 화면에 보일 글로 바꾼다. 순수한 함수다. 값은 모두 서버가 준 것이다. 화면이 판정을 계산하지 않는다.
// 이번에는 판정(check)의 결과만 자세히 적는다. 다른 행동은 이름만 적는다(일어난 일은 ④ 에서 보인다).

import type { Declaration, Round, Ruleset } from '../../../../api/types';

type Action = NonNullable<Declaration['action']>;
type Outcome = NonNullable<Declaration['outcome']>;

const ACTION_LABELS: Record<Action['kind'], string> = {
  check: '판정',
  treat: '치료',
  name: '지목',
  use: '물건 쓰기',
  give: '건네기',
  move: '가기',
  search: '찾기',
  rest: '쉬기',
  take: '줍기',
  put_down: '내려놓기',
  steal: '훔치기',
  loot: '빼앗기',
  wait: '기다리기',
};

const ROUND_STATUS: Record<Round['status'], string> = {
  open: '선언을 받는 중',
  closing: '결과를 서술하는 중',
  closed: '끝난 라운드',
};

const FATES: Record<Round['death_saves'][number]['fate'], string> = {
  dying: '아직 위태롭다',
  stable: '고비를 넘겼다',
  dead: '죽었다',
};

export function roundStatusLabel(status: Round['status']): string {
  return ROUND_STATUS[status];
}

/** "판정 · 근력, 보통". 판정이 아니면 행동의 이름만 */
export function actionLabel(action: Action, rules: Ruleset): string {
  const label = ACTION_LABELS[action.kind];
  if (action.kind !== 'check') return label;
  const ability = rules.abilities.find((entry) => entry.key === action.ability)?.name ?? action.ability;
  const key = action.difficulty ?? rules.default_difficulty;
  const difficulty = rules.difficulties.find((entry) => entry.key === key)?.name ?? key;
  return `${label} · ${ability}, ${difficulty}`;
}

/** 결과 한 줄. 판정은 눈과 보정, 합, 목표, 성공. 행동하지 못했거나 대상이 사라졌으면 그렇게. 결과가 없으면 null */
export function outcomeLine(outcome: Outcome | null): string | null {
  if (!outcome) return null;
  if ('turn_lost' in outcome) return '행동하지 못했습니다.';
  if ('target_gone' in outcome) return '대상이 이미 없어 행동하지 못했습니다.';
  if ('roll' in outcome && 'total' in outcome && 'success' in outcome) return checkLine(outcome);
  return '결과는 일어난 일에 적힙니다.';
}

type CheckResult = Extract<Outcome, { roll: number; total: number }>;

function checkLine(outcome: CheckResult): string {
  const modifier = outcome.modifier >= 0 ? `+${outcome.modifier}` : String(outcome.modifier);
  const parts = [`눈 ${outcome.roll}, 보정 ${modifier}, 합 ${outcome.total} / 목표 ${outcome.target}`];
  if (outcome.hindrance?.disadvantage) parts.push('불리함');
  if (outcome.called_shot) parts.push('노려 치기');
  parts.push(outcome.success ? '성공' : '실패');
  return parts.join(' · ');
}

/** 죽음의 굴림 한 줄. "렌: 죽음의 굴림 12 / 10 성공 (성공 2, 실패 1) · 아직 위태롭다" */
export function deathSaveLine(save: Round['death_saves'][number]): string {
  const result = save.success ? '성공' : '실패';
  return `${save.character_name}: 죽음의 굴림 ${save.roll} / ${save.target} ${result} (성공 ${save.successes}, 실패 ${save.failures}) · ${FATES[save.fate]}`;
}

/** 지금 라운드를 뺀 최근의 라운드들. 오래된 것부터 */
export function pastRounds(recent: Round[], current: Round | undefined): Round[] {
  if (!current) return recent;
  return recent.filter((round) => round.number < current.number);
}

/** 내 선언. 선언을 받는 동안에도 내 것은 글이 보인다. 내지 않았으면 undefined */
export function myDeclaration(round: Round, myId: string | undefined): Declaration | undefined {
  return round.declarations.find((declaration) => declaration.user_id === myId && declaration.content !== null);
}

/** 마감까지 남은 초. 마감이 없으면 null, 지났으면 0 */
export function remainingSeconds(deadlineAt: string | null, now: number): number | null {
  if (!deadlineAt) return null;
  return Math.max(0, Math.ceil((Date.parse(deadlineAt) - now) / 1000));
}
