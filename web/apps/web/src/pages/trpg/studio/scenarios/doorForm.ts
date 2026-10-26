// web/apps/web/src/pages/trpg/studio/scenarios/doorForm.ts
// 길의 문(#281)의 입력. 넘기 판정(cross), 자물쇠(lock)와 따기(pick), 빗장(bar), 부수기(force), 고치기(repair). 순수한 함수다.
//
// 서버의 검사(RouteRule, 게시의 route_* 문제)를 따른다:
//   - 판정의 능력치는 꼭 고른다. 난이도를 비우면 룰북의 기본이다. 넘기의 피해(양의 등급)는 비워도 된다
//   - 자물쇠는 열쇠(물건 항목)가 꼭 있다. 열쇠 하나는 자물쇠 하나만 연다(다른 길이나 자물쇠 물건에 같은 열쇠면 route_key_repeated)
//   - 빗장은 길의 두 끝 중 한쪽에 있다
//   - 부수기와 고치기는 자물쇠나 빗장이 있는 길에만 적는다. 둘 다 끄면 함께 비운다
//   - 따기와 고치기는 도구가 있어야 하는지(needs_tool, #802)를 고른다. 어느 물건이 거드는지는 물건 규칙의 거들기가 정한다

import type { RouteRule, RouteRuleBody } from '../../../../api/types';

type Check = { ability: string; difficulty: string };

export type DoorDraft = {
  cross: Check & { on: boolean; harm: string };
  lock: { on: boolean; key: string; locked: boolean };
  pick: Check & { on: boolean; needsTool: boolean };
  bar: { on: boolean; side: string; barred: boolean };
  force: Check & { on: boolean };
  repair: Check & { on: boolean; needsTool: boolean };
};

export function doorDraft(route: RouteRule): DoorDraft {
  return {
    cross: { on: route.cross != null, ability: route.cross?.ability ?? '', difficulty: route.cross?.difficulty ?? '', harm: route.cross?.harm ?? '' },
    lock: { on: route.lock != null, key: route.lock?.key ?? '', locked: route.lock?.locked ?? true },
    pick: {
      on: route.lock?.pick != null,
      ability: route.lock?.pick?.ability ?? '',
      difficulty: route.lock?.pick?.difficulty ?? '',
      needsTool: route.lock?.pick?.needs_tool ?? false,
    },
    bar: { on: route.bar != null, side: route.bar?.side ?? route.from_place, barred: route.bar?.barred ?? false },
    force: { on: route.force != null, ability: route.force?.ability ?? '', difficulty: route.force?.difficulty ?? '' },
    repair: {
      on: route.repair != null,
      ability: route.repair?.ability ?? '',
      difficulty: route.repair?.difficulty ?? '',
      needsTool: route.repair?.needs_tool ?? false,
    },
  };
}

/** 보내기 전에 알릴 것. at 은 이 길의 차례(다른 길의 열쇠와 견준다). itemKeys 는 자물쇠 물건들의 열쇠 */
export function doorHints(draft: DoorDraft, routes: RouteRule[], at: number, itemKeys: string[] = []): Record<string, string> {
  const hints: Record<string, string> = {};
  const route = routes[at];
  if (draft.cross.on && draft.cross.ability === '') hints.cross = '넘기 판정의 능력치를 골라 주세요.';
  if (draft.lock.on) {
    if (draft.lock.key === '') hints.lock = '자물쇠를 여는 열쇠(물건)를 골라 주세요.';
    else if (routes.some((other, index) => index !== at && other.lock?.key === draft.lock.key)) hints.lock = '이 열쇠는 다른 길의 자물쇠를 엽니다. 열쇠 하나는 자물쇠 하나만 엽니다.';
    else if (itemKeys.includes(draft.lock.key)) hints.lock = '이 열쇠는 자물쇠 물건의 새 자물쇠를 엽니다. 열쇠 하나는 자물쇠 하나만 엽니다.';
    if (draft.pick.on && draft.pick.ability === '') hints.pick = '따기 판정의 능력치를 골라 주세요.';
  }
  if (draft.bar.on && route && ![route.from_place, route.to_place].includes(draft.bar.side)) hints.bar = '빗장은 길의 두 끝 중 한쪽에 있어야 합니다.';
  if (draft.force.on) {
    if (!draft.lock.on && !draft.bar.on) hints.force = '부수기는 자물쇠나 빗장이 있는 길에만 적습니다.';
    else if (draft.force.ability === '') hints.force = '부수기 판정의 능력치를 골라 주세요.';
  }
  if (draft.repair.on) {
    if (!draft.lock.on && !draft.bar.on) hints.repair = '고치기는 자물쇠나 빗장이 있는 길에만 적습니다.';
    else if (draft.repair.ability === '') hints.repair = '고치기 판정의 능력치를 골라 주세요.';
  }
  return hints;
}

/** 이 길의 문만 바꾼 목록. 끈 것은 null 로 비운다. 힌트가 없을 때만 부른다 */
export function withDoor(routes: RouteRule[], at: number, draft: DoorDraft): RouteRuleBody[] {
  const hasDoor = draft.lock.on || draft.bar.on;
  const door: Pick<RouteRuleBody, 'cross' | 'lock' | 'bar' | 'force' | 'repair'> = {
    cross: draft.cross.on ? { ability: draft.cross.ability, difficulty: draft.cross.difficulty || null, harm: draft.cross.harm || null } : null,
    lock: draft.lock.on
      ? {
          key: draft.lock.key,
          locked: draft.lock.locked,
          pick: draft.pick.on ? { ability: draft.pick.ability, difficulty: draft.pick.difficulty || null, needs_tool: draft.pick.needsTool } : null,
        }
      : null,
    bar: draft.bar.on ? { side: draft.bar.side, barred: draft.bar.barred } : null,
    force: draft.force.on && hasDoor ? { ability: draft.force.ability, difficulty: draft.force.difficulty || null } : null,
    repair: draft.repair.on && hasDoor ? { ability: draft.repair.ability, difficulty: draft.repair.difficulty || null, needs_tool: draft.repair.needsTool } : null,
  };
  return routes.map((route, index) => (index === at ? { ...route, ...door } : route));
}
