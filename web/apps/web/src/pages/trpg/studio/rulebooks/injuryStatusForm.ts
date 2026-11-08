// web/apps/web/src/pages/trpg/studio/rulebooks/injuryStatusForm.ts
// 룰북의 짧은 부상(상태 이상)의 라운드마다의 피해와 벗어나기(#254) 입력. 화면을 그리지 않는 순수한 함수다.
//
//   - 부상 자체(이름, 효과, 라운드 수)는 템플릿의 것이다. 여기서는 짧은 것(healing rounds)의 두 칸만 고친다
//   - 피해(damage)는 규칙의 피해 등급과, 고르면 성질 하나다. 등급을 비우면 피해가 없다(성질도 보내지 않는다)
//   - 벗어나기(escape)는 능력치와, 고르면 난이도다. 능력치를 비우면 벗어날 수 없다. 난이도를 비우면 기본 난이도다
//   - 고르는 칸만 있어 틀린 값을 적을 수 없다. 그래서 보내기 전의 검사가 없다. 서버는 규칙 전체로 다시 본다(422)
//   - 보낼 때는 부상 목록을 통째로 보낸다(서버가 통째로 바꾼다). 짧은 것이 아닌 부상은 받은 그대로다

import type { Injury, Ruleset } from '../../../../api/types';

/** 고를 거리를 정하는 규칙의 칸들. 템플릿이나 룰북의 규칙에서 온다 */
export type StatusRules = Pick<Ruleset, 'injuries' | 'magnitudes' | 'natures' | 'abilities' | 'difficulties'>;

/** 짧은 부상 하나의 고칠 거리. 빈 글은 "고르지 않음"이다 */
export type StatusRow = { key: string; name: string; magnitude: string; nature: string; ability: string; difficulty: string };

export type StatusDraft = { rules: StatusRules; rows: StatusRow[] };

/** 상태(짧은 부상)인가. 라운드로 세는 것만 피해와 벗어나기가 있다 */
export function isShort(injury: Injury): boolean {
  return injury.healing === 'rounds';
}

function rowOf(injury: Injury): StatusRow {
  return {
    key: injury.key,
    name: injury.name,
    magnitude: injury.damage?.magnitude ?? '',
    nature: injury.damage?.nature ?? '',
    ability: injury.escape?.ability ?? '',
    difficulty: injury.escape?.difficulty ?? '',
  };
}

/** 규칙의 부상들을 고칠 거리로. 짧은 것만 줄이 된다. 규칙의 차례다 */
export function statusDraft(rules: StatusRules): StatusDraft {
  return { rules, rows: rules.injuries.filter(isShort).map(rowOf) };
}

/** 줄 하나를 바꾼다. 피해의 등급을 비우면 성질도 비운다(등급 없는 성질은 보내지 않는다) */
export function withRow(draft: StatusDraft, key: string, changes: Partial<StatusRow>): StatusDraft {
  const rows = draft.rows.map((row) => {
    if (row.key !== key) return row;
    const next = { ...row, ...changes };
    return next.magnitude === '' ? { ...next, nature: '' } : next;
  });
  return { ...draft, rows };
}

function damageOf(row: StatusRow): Injury['damage'] {
  return row.magnitude === '' ? null : { magnitude: row.magnitude, nature: row.nature === '' ? null : row.nature };
}

function escapeOf(row: StatusRow): Injury['escape'] {
  return row.ability === '' ? null : { ability: row.ability, difficulty: row.difficulty === '' ? null : row.difficulty };
}

/** 보낼 부상 목록. 짧은 것에는 고른 피해와 벗어나기를 싣고, 나머지는 받은 그대로다 */
export function toInjuries(draft: StatusDraft): Injury[] {
  return draft.rules.injuries.map((injury) => {
    const row = draft.rows.find((one) => one.key === injury.key);
    return row ? { ...injury, damage: damageOf(row), escape: escapeOf(row) } : injury;
  });
}

/** 피해 등급의 보일 이름. "가벼운 피해(1d4)" */
export function magnitudeLabel(magnitude: StatusRules['magnitudes'][number]): string {
  const dice = `${magnitude.count === 1 ? '' : magnitude.count}d${magnitude.sides}`;
  return `${magnitude.name}(${dice})`;
}
