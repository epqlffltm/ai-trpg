// web/apps/web/src/pages/limited/reconsent.ts
// 다시 동의의 화면이 쓰는 순수한 함수. 무엇을 받을지, 다 체크했는지.

import type { ConsentState } from '../../api/types';

/** 다시 동의할 항목(서버가 pending 으로 표시한 필수 항목) */
export function pendingItems(states: ConsentState[]): ConsentState[] {
  return states.filter((state) => state.pending);
}

/** 받을 항목을 모두 체크했는가. 받을 것이 없으면 거짓이다(누를 것이 없다) */
export function allChecked(items: ConsentState[], checked: Record<string, boolean>): boolean {
  return items.length > 0 && items.every((state) => checked[state.item]);
}
