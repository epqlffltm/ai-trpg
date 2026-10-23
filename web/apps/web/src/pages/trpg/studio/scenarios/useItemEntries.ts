// web/apps/web/src/pages/trpg/studio/scenarios/useItemEntries.ts
// 시나리오에 붙인 로어북들의 물건 항목(B9 물건·돈 탭). 로어북마다 항목을 읽어(entriesQuery) 물건만 모은다.
// 물건 규칙, 시작 소지품, 프리젠의 소지품이 모두 이 항목을 가리킨다. 저장된 로어북 목록을 따른다(재료 탭의 저장 전 고침은 아니다).

import { useQueries } from '@tanstack/react-query';
import type { LoreEntry } from '../../../../api/types';
import { entriesQuery } from '../lorebooks/lorebookQueries';

export type ItemEntry = { id: string; name: string };

/** 로어북들의 항목에서 물건만. 붙인 차례, 로어북 안의 차례를 지킨다 */
export function itemEntriesOf(entryLists: (LoreEntry[] | undefined)[]): ItemEntry[] {
  return entryLists.flatMap((entries) => (entries ?? []).filter((entry) => entry.kind === 'item').map(({ id, name }) => ({ id, name })));
}

export function useItemEntries(lorebookIds: string[]) {
  const results = useQueries({ queries: lorebookIds.map((lorebookId) => entriesQuery(lorebookId)) });
  return {
    entries: itemEntriesOf(results.map((result) => result.data)),
    pending: results.some((result) => result.isPending),
    failed: results.some((result) => result.isError),
  };
}

/** 항목의 이름. 붙인 로어북에 없으면(뗐거나 지웠다) 그렇다고 적는다 */
export function entryName(entries: ItemEntry[], entryId: string): string {
  return entries.find((entry) => entry.id === entryId)?.name ?? '(붙인 로어북에 없는 물건)';
}
