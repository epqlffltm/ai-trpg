// web/apps/web/src/pages/trpg/room/status/growthView.ts
// 성장(#286)을 상태 패널에 보일 글과, 쌓인 점수를 능력치에 놓는 창의 계산. 순수한 함수다.
// 경험치, 레벨, 다음 레벨, 쌓인 점수는 모두 서버가 준 것이다(SheetOut). 화면은 레벨을 계산하지 않는다.
// 놓기의 검사(점수가 모자람, 상한)는 창이 단추를 끄려고 미리 볼 뿐이고, 정하는 것은 서버다(app/tables/growth.py).

import type { Round, Ruleset, Sheet, TableDetail, TableMember } from '../../../../api/types';

/** 능력치의 이름표 → 놓을 점수. 0 인 것은 두지 않는다 */
export type Raises = Record<string, number>;

/** "레벨 3 · 경험치 450 / 900". 마지막 레벨이면 "레벨 20 · 경험치 9,000 · 마지막 레벨". 성장이 없는 규칙이면 null */
export function levelLine(sheet: Sheet, rules: Ruleset): string | null {
  if (!rules.progression) return null;
  const xp = sheet.xp.toLocaleString('ko-KR');
  if (sheet.next_level_xp == null) return `레벨 ${sheet.level} · 경험치 ${xp} · 마지막 레벨`;
  return `레벨 ${sheet.level} · 경험치 ${xp} / ${sheet.next_level_xp.toLocaleString('ko-KR')}`;
}

/** 다음 레벨까지의 비율(0~1). 마지막 레벨이면 1. 막대의 길이에 쓴다 */
export function levelRatio(sheet: Sheet, rules: Ruleset): number {
  if (sheet.next_level_xp == null) return 1;
  const levels = rules.progression?.levels ?? [];
  // 지금 레벨이 된 누적 경험치. 레벨 1 은 0 이고, 레벨표의 첫 줄이 레벨 2 다
  const floor = sheet.level >= 2 ? (levels[sheet.level - 2]?.xp ?? 0) : 0;
  const span = sheet.next_level_xp - floor;
  if (span <= 0) return 0;
  return Math.min(1, Math.max(0, (sheet.xp - floor) / span));
}

/** 점수를 놓을 수 있는가. 진행 중이고, 라운드가 선언을 받는 중이고, 내 캐릭터가 살아 있고, 점수가 있다(쓰러져도 놓는다) */
export function canRaise(table: TableDetail, me: TableMember | undefined, round: Round | undefined): boolean {
  if (table.status !== 'playing' || round?.status !== 'open') return false;
  return Boolean(me?.sheet && !me.sheet.dead && me.sheet.points > 0);
}

/** 고른 것에 든 점수 */
export function spent(raises: Raises): number {
  return Object.values(raises).reduce((sum, amount) => sum + amount, 0);
}

/** 그 능력치를 하나 더 올릴 수 있는가. 남은 점수가 있고 상한(score_max)을 넘지 않는다 */
export function canStepUp(raises: Raises, key: string, sheet: Sheet, rules: Ruleset): boolean {
  const score = (sheet.abilities[key] ?? 0) + (raises[key] ?? 0);
  return spent(raises) < sheet.points && score < rules.score_max;
}

/** 그 능력치에 놓은 것을 하나 올리거나(+1) 내린다(-1). 할 수 없으면 그대로. 0 이 되면 뺀다 */
export function stepped(raises: Raises, key: string, delta: 1 | -1, sheet: Sheet, rules: Ruleset): Raises {
  if (delta === 1 && !canStepUp(raises, key, sheet, rules)) return raises;
  const next = (raises[key] ?? 0) + delta;
  if (next < 0) return raises;
  const rest = Object.fromEntries(Object.entries(raises).filter(([one]) => one !== key));
  return next === 0 ? rest : { ...rest, [key]: next };
}

/** 고른 것을 한 줄로. "근력 12 → 13, 건강 10 → 12". 규칙의 능력치 차례다 */
export function raisesLine(raises: Raises, sheet: Sheet, rules: Ruleset): string {
  return rules.abilities
    .filter((ability) => (raises[ability.key] ?? 0) > 0)
    .map((ability) => {
      const from = sheet.abilities[ability.key] ?? 0;
      return `${ability.name} ${from} → ${from + (raises[ability.key] ?? 0)}`;
    })
    .join(', ');
}
