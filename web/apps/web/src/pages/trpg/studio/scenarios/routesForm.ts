// web/apps/web/src/pages/trpg/studio/scenarios/routesForm.ts
// 지도 탭의 길(B9). 길은 장소 둘을 잇는다. 순수한 함수다(서버의 RouteRule 검사를 따른다).
//
// - 두 끝은 다른 장소다. 같은 두 장소를 잇는 길은 하나뿐이다(방향이 달라도 같다)
// - 보임: 처음부터 앎(open), 끝에 서 보면 앎(fog), 찾아야 앎(hidden). 숨긴 길만 찾는 판정(능력치, 난이도)이 있다
// - 걸리는 시간(분)은 비우면 라운드의 걸음 안이다(옆방). 1~10080
// - 길의 문(넘기, 자물쇠, 빗장, 부수기)은 다음 화면에서 고친다. 여기서는 그대로 둔다. 빗장이 있으면 그 끝은 바꾸지 못한다

import type { RouteRule, RouteRuleBody, RouteVisibility, Ruleset } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';
import { ROUND_MAX_MINUTES } from './basicsForm';

export const MAX_ROUTES = 200;

const VISIBILITIES: Record<RouteVisibility, string> = { open: '처음부터 앎', fog: '끝에 서 보면 앎', hidden: '찾아야 앎(숨긴 길)' };

export const VISIBILITY_VALUES = Object.keys(VISIBILITIES) as RouteVisibility[];

export function visibilityLabel(visibility: RouteVisibility): string {
  return VISIBILITIES[visibility];
}

export type RouteDraft = {
  from: string;
  to: string;
  twoWay: boolean;
  visibility: RouteVisibility;
  findAbility: string;
  findDifficulty: string;
  minutes: string;
};

/** 창의 처음 값. 새 길이면 숨기지 않고 양쪽으로 다니는 길 */
export function routeDraft(route: RouteRule | null): RouteDraft {
  return {
    from: route?.from_place ?? '',
    to: route?.to_place ?? '',
    twoWay: route?.two_way ?? true,
    visibility: route?.visibility ?? 'open',
    findAbility: route?.find?.ability ?? '',
    findDifficulty: route?.find?.difficulty ?? '',
    minutes: route?.travel_minutes ? String(route.travel_minutes) : '',
  };
}

function samePair(route: RouteRule, from: string, to: string): boolean {
  return (route.from_place === from && route.to_place === to) || (route.from_place === to && route.to_place === from);
}

/** 보내기 전에 알릴 것. at 은 고치는 길의 차례(새 길이면 null) */
export function routeHints(draft: RouteDraft, routes: RouteRule[], at: number | null): Record<string, string> {
  const hints: Record<string, string> = {};
  const original = at === null ? null : routes[at];
  if (draft.from === '' || draft.to === '') hints.ends = '길의 두 끝을 골라 주세요.';
  else if (draft.from === draft.to) hints.ends = '길의 두 끝이 같은 장소입니다.';
  else if (routes.some((route, index) => index !== at && samePair(route, draft.from, draft.to))) hints.ends = '이 두 장소를 잇는 길이 이미 있습니다.';
  else if (original?.bar && ![draft.from, draft.to].includes(original.bar.side)) hints.ends = '빗장이 있는 끝은 바꿀 수 없습니다. 문을 먼저 고쳐 주세요.';
  if (draft.visibility === 'hidden' && draft.findAbility === '') hints.find = '숨긴 길은 찾는 판정의 능력치를 골라 주세요.';
  if (draft.minutes.trim() !== '' && wholeNumber(draft.minutes, 1, ROUND_MAX_MINUTES) === null) hints.minutes = `1~${ROUND_MAX_MINUTES} 사이의 정수입니다. 비우면 옆방처럼 걸음 안에 갑니다.`;
  return hints;
}

/** 보낼 길. 숨긴 길에만 찾는 판정을 싣는다. 원래 길의 문(넘기, 자물쇠, 빗장, 부수기)은 그대로 둔다 */
export function toRoute(draft: RouteDraft, original: RouteRule | null): RouteRuleBody {
  return {
    from_place: draft.from,
    to_place: draft.to,
    two_way: draft.twoWay,
    visibility: draft.visibility,
    find: draft.visibility === 'hidden' ? { ability: draft.findAbility, difficulty: draft.findDifficulty || null } : null,
    travel_minutes: draft.minutes.trim() === '' ? null : Number(draft.minutes.trim()),
    cross: original?.cross ?? null,
    lock: original?.lock ?? null,
    bar: original?.bar ?? null,
    force: original?.force ?? null,
  };
}

export function withRoute(routes: RouteRule[], at: number | null, route: RouteRuleBody): RouteRuleBody[] {
  return at === null ? [...routes, route] : routes.map((one, index) => (index === at ? route : one));
}

export function withoutRoute(routes: RouteRule[], at: number): RouteRuleBody[] {
  return routes.filter((_, index) => index !== at);
}

/** 목록의 한 줄. "수도원 문 ↔ 종탑 · 끝에 서 보면 앎 · 30분 · 문 있음" */
export function routeLine(route: RouteRule, nameOf: (placeId: string) => string, rules: Ruleset | null): string {
  const arrow = route.two_way ? '↔' : '→';
  const parts = [`${nameOf(route.from_place)} ${arrow} ${nameOf(route.to_place)}`, visibilityLabel(route.visibility)];
  if (route.find) {
    const ability = rules?.abilities.find((one) => one.key === route.find?.ability)?.name ?? route.find.ability;
    parts.push(`찾기: ${ability}`);
  }
  if (route.travel_minutes) parts.push(`${route.travel_minutes}분`);
  if (route.lock || route.bar) parts.push('문 있음');
  if (route.cross) parts.push('넘기 판정');
  return parts.join(' · ');
}
