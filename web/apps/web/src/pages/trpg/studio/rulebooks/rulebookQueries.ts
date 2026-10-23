// web/apps/web/src/pages/trpg/studio/rulebooks/rulebookQueries.ts
// 룰북 화면(B9)이 읽는 것의 열쇠와 부르는 함수. 열쇠의 앞(RULEBOOKS_KEY)을 무르면 목록과 낱개가 함께 다시 읽힌다.

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { fetchRulebook, fetchRulebooks, fetchRulebookTemplates } from '../../../../api/rulebooks';
import { nextOffset, PAGE_SIZE } from '../../queries';

export const RULEBOOKS_KEY = ['trpg', 'studio', 'rulebooks'] as const;

/** 내 룰북의 목록. 최근에 만든 것부터 한 쪽씩 */
export function rulebooksQuery() {
  return infiniteQueryOptions({
    queryKey: [...RULEBOOKS_KEY, 'list'],
    queryFn: ({ pageParam, signal }) => fetchRulebooks({ limit: PAGE_SIZE, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => nextOffset(lastPage.total, allPages.length),
  });
}

export function rulebookQuery(rulebookId: string) {
  return queryOptions({
    queryKey: [...RULEBOOKS_KEY, 'detail', rulebookId],
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
