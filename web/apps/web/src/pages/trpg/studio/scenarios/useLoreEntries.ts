// web/apps/web/src/pages/trpg/studio/scenarios/useLoreEntries.ts
// 시나리오에 붙인 로어북들의 항목 가운데 한 종류(물건, 인물 …). 로어북마다 항목을 읽어(entriesQuery) 그 종류만 모은다.
// 물건 규칙과 소지품은 물건 항목을, 인물 시트는 인물 항목을 가리킨다. 저장된 로어북 목록을 따른다(재료 탭의 저장 전 고침은 아니다).

import { useQueries } from '@tanstack/react-query';
import type { LoreEntry, LoreKind } from '../../../../api/types';
import { entriesQuery } from '../lorebooks/lorebookQueries';

export type EntryChoice = { id: string; name: string };

/** 로어북들의 항목에서 그 종류만. 붙인 차례, 로어북 안의 차례를 지킨다 */
export function entriesOfKind(entryLists: (LoreEntry[] | undefined)[], kind: LoreKind): EntryChoice[] {
  return entryLists.flatMap((entries) => (entries ?? []).filter((entry) => entry.kind === kind).map(({ id, name }) => ({ id, name })));
}

export function useLoreEntries(lorebookIds: string[], kind: LoreKind) {
  const results = useQueries({ queries: lorebookIds.map((lorebookId) => entriesQuery(lorebookId)) });
  return {
    entries: entriesOfKind(
      results.map((result) => result.data),
      kind,
    ),
    pending: results.some((result) => result.isPending),
    failed: results.some((result) => result.isError),
  };
}

/** 물건 항목의 이름. 붙인 로어북에 없으면(뗐거나 지웠다) 그렇다고 적는다 */
export function entryName(entries: EntryChoice[], entryId: string): string {
  return entries.find((entry) => entry.id === entryId)?.name ?? '(붙인 로어북에 없는 물건)';
}
