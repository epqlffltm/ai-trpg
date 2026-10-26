// web/apps/web/src/pages/operator/moderationQueries.ts
// 신고 처리(E4)가 읽는 것의 열쇠. 모두 ['operator', 'reports'] 아래에 둔다. 처리하면 그 앞을 물러 목록을 다시 읽는다.
// 대화 속 답의 신고 하나는 여기 두지 않는다. 볼 때마다 감사 기록이 남아 저절로 다시 읽으면 안 된다(MessageReportPage).

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { BOARD_REPORT_PAGE_SIZE, fetchBoardItemReports, fetchBoardReportGroups, type ReportedItem } from '../../api/boardReports';
import { fetchCharacterReportGroups, fetchCharacterReports, fetchMessageReports } from '../../api/moderation';
import { nextOffset, nextPage, PAGE_SIZE } from './moderationPure';

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

/** 게시판의 신고. 쪽 번호로 이어 읽는다 */
export function boardGroupsQuery() {
  return infiniteQueryOptions({
    queryKey: [...REPORTS_KEY, 'board'] as const,
    queryFn: ({ pageParam, signal }) => fetchBoardReportGroups(pageParam, signal),
    initialPageParam: 1,
    getNextPageParam: (lastPage, allPages) => nextPage(lastPage.total, allPages.length, BOARD_REPORT_PAGE_SIZE),
  });
}

export function boardItemReportsQuery(item: ReportedItem) {
  return infiniteQueryOptions({
    queryKey: [...REPORTS_KEY, 'board', item.type, item.id] as const,
    queryFn: ({ pageParam, signal }) => fetchBoardItemReports(item, pageParam, signal),
    initialPageParam: 1,
    getNextPageParam: (lastPage, allPages) => nextPage(lastPage.total, allPages.length, BOARD_REPORT_PAGE_SIZE),
  });
}
