// web/apps/web/src/pages/trpg/studio/bestiaries/bestiaryQueries.ts
// 몬스터 모음의 몬스터 읽기(B9). 몬스터의 열쇠는 모음의 낱개 열쇠 아래에 있다(itemsKey). 모음 자신은 CollectionEditPage 가 읽는다.

import { queryOptions } from '@tanstack/react-query';
import { fetchMonsters } from '../../../../api/bestiaries';
import { itemsKey } from '../collection/useItemActions';

export function monstersQuery(bestiaryId: string) {
  return queryOptions({
    queryKey: itemsKey('bestiaries', bestiaryId),
    queryFn: ({ signal }) => fetchMonsters(bestiaryId, signal),
  });
}
