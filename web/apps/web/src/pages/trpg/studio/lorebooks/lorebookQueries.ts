// web/apps/web/src/pages/trpg/studio/lorebooks/lorebookQueries.ts
// 로어북의 항목 읽기(B9). 항목의 열쇠는 로어북의 낱개 열쇠 아래에 있다(itemsKey). 로어북 자신은 CollectionEditPage 가 읽는다.

import { queryOptions } from '@tanstack/react-query';
import { fetchEntries } from '../../../../api/lorebooks';
import { itemsKey } from '../collection/useItemActions';

export function entriesQuery(lorebookId: string) {
  return queryOptions({
    queryKey: itemsKey('lorebooks', lorebookId),
    queryFn: ({ signal }) => fetchEntries(lorebookId, signal),
  });
}
