// web/apps/web/src/pages/operator/moderationQueries.ts
// 신고 처리(E4)가 읽는 것의 열쇠. 모두 ['operator', 'reports'] 아래에 둔다. 처리하면 그 앞을 물러 목록을 다시 읽는다.
// 대화 속 답의 신고 하나는 여기 두지 않는다. 볼 때마다 감사 기록이 남아 저절로 다시 읽으면 안 된다(MessageReportPage).

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { fetchCharacterReportGroups, fetchCharacterReports, fetchMessageReports } from '../../api/moderation';
import { nextOffset, PAGE_SIZE } from './moderationPure';

export const REPORTS_KEY = ['operator', 'reports'] as const;

export function characterGroupsQuery() {
  return infiniteQueryOptions({
    queryKey: [...REPORTS_KEY, 'characters'] as const,
    queryFn: ({ pageParam, signal }) => fetchCharacterReportGroups({ limit: PAGE_SIZE, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => nextOffset(lastPage.total, allPages.length),
  });
}

export function characterReportsQuery(characterId: string) {
  return queryOptions({
    queryKey: [...REPORTS_KEY, 'characters', characterId] as const,
    queryFn: ({ signal }) => fetchCharacterReports(characterId, signal),
  });
}

export function messageReportsQuery() {
  return infiniteQueryOptions({
    queryKey: [...REPORTS_KEY, 'messages'] as const,
    queryFn: ({ pageParam, signal }) => fetchMessageReports({ limit: PAGE_SIZE, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => nextOffset(lastPage.total, allPages.length),
  });
}
