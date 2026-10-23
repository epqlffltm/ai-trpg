// web/apps/web/src/pages/trpg/studio/rulebooks/rulebookQueries.ts
// 룰북 화면(B9)이 읽는 것의 열쇠와 부르는 함수. 목록은 재료가 함께 쓴다(studioQueries.ts).

import { queryOptions } from '@tanstack/react-query';
import { fetchRulebook, fetchRulebookTemplates } from '../../../../api/rulebooks';
import { assetDetailKey } from '../studioQueries';

export function rulebookQuery(rulebookId: string) {
  return queryOptions({
    queryKey: assetDetailKey('rulebooks', rulebookId),
    queryFn: ({ signal }) => fetchRulebook(rulebookId, signal),
  });
}

/** 템플릿은 서버의 파일이라 잘 바뀌지 않는다. 한 번 읽으면 이 창에서는 다시 읽지 않는다 */
export function rulebookTemplatesQuery() {
  return queryOptions({
    queryKey: ['trpg', 'studio', 'rulebook-templates'],
    queryFn: ({ signal }) => fetchRulebookTemplates(signal),
    staleTime: Infinity,
  });
}
