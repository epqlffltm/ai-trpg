// web/apps/web/src/pages/trpg/studio/scenarios/itemLockForm.ts
// 자물쇠 물건(#281)의 입력. 물건 규칙의 lock(새 열쇠, 따는 판정과 도구). 순수한 함수다(서버의 ItemLock, 게시의 route_key_repeated 를 따른다).
//
// - 장비에만 적는다. 행동 '자물쇠 바꾸기'로 판에 자물쇠가 있던 문에 달고, 달면 소지품에서 없어진다
// - 새 열쇠(물건 항목)는 꼭 있다. 자물쇠 물건 자신은 열쇠가 될 수 없다
// - 열쇠 하나는 자물쇠 하나만 연다. 길의 자물쇠의 열쇠, 다른 자물쇠 물건의 열쇠와 겹치지 못한다
// - 따는 판정은 능력치를 꼭 고른다. 난이도를 비우면 룰북의 기본이다. 도구는 비워도 된다

import type { ItemRule, ItemRuleBody, RouteRule } from '../../../../api/types';

export type ItemLockDraft = {
  on: boolean;
  key: string;
  pick: { on: boolean; ability: string; difficulty: string; tool: string };
};

type ItemLockBody = NonNullable<ItemRuleBody['lock']>;

export function itemLockDraft(lock: ItemRule['lock']): ItemLockDraft {
  return {
    on: lock != null,
    key: lock?.key ?? '',
    pick: { on: lock?.pick != null, ability: lock?.pick?.ability ?? '', difficulty: lock?.pick?.difficulty ?? '', tool: lock?.pick?.tool ?? '' },
  };
}

/** 이 물건 말고 다른 자물쇠(길의 자물쇠, 다른 자물쇠 물건)의 열쇠들 */
export function keysElsewhere(routes: RouteRule[], items: ItemRule[], entryId: string): string[] {
  const routeKeys = routes.flatMap((route) => (route.lock ? [route.lock.key] : []));
  const itemKeys = items.flatMap((rule) => (rule.entry_id !== entryId && rule.lock ? [rule.lock.key] : []));
  return [...routeKeys, ...itemKeys];
}

/** 보내기 전에 알릴 것. 칸 이름(lock, lock_pick) → 글. 끈 자물쇠는 보지 않는다 */
export function itemLockHints(draft: ItemLockDraft, entryId: string, otherKeys: string[]): Record<string, string> {
  if (!draft.on) return {};
  const hints: Record<string, string> = {};
  if (draft.key === '') hints.lock = '새 자물쇠를 여는 열쇠(물건)를 골라 주세요.';
  else if (draft.key === entryId) hints.lock = '자물쇠 물건 자신은 열쇠가 될 수 없습니다. 달면 없어집니다.';
  else if (otherKeys.includes(draft.key)) hints.lock = '이 열쇠는 다른 자물쇠(길의 자물쇠나 자물쇠 물건)를 엽니다. 열쇠 하나는 자물쇠 하나만 엽니다.';
  if (draft.pick.on && draft.pick.ability === '') hints.lock_pick = '따기 판정의 능력치를 골라 주세요.';
  return hints;
}

/** 보낼 자물쇠. 끈 것은 null */
export function toItemLock(draft: ItemLockDraft): ItemLockBody | null {
  if (!draft.on) return null;
  const pick = draft.pick.on ? { ability: draft.pick.ability, difficulty: draft.pick.difficulty || null, tool: draft.pick.tool || null } : null;
  return { key: draft.key, pick };
}
