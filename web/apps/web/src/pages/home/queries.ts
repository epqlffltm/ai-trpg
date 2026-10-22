// web/apps/web/src/pages/home/queries.ts
// 첫 화면이 읽는 것들의 열쇠와 부르는 함수. 줄마다 열쇠가 따로라서 따로 불러오고 따로 실패한다.
// 공개 목록은 로그인했는지에 따라 내용이 다르다(로그인 전에는 전체이용가만). 그래서 열쇠에 그것을 넣는다.

import { queryOptions } from '@tanstack/react-query';
import { fetchMyConversations, fetchMyTables, fetchPublicCharacters, fetchPublicScenarios } from '../../api/lists';

/** 줄마다 보이는 수 */
export const ROW_LIMIT = 6;

export function publicScenariosQuery(signedIn: boolean) {
  return queryOptions({
    queryKey: ['trpg', 'listings', { signedIn, limit: ROW_LIMIT }],
    queryFn: ({ signal }) => fetchPublicScenarios(ROW_LIMIT, signal),
  });
}

export function publicCharactersQuery(signedIn: boolean) {
  return queryOptions({
    queryKey: ['chat', 'characters', { signedIn, limit: ROW_LIMIT }],
    queryFn: ({ signal }) => fetchPublicCharacters(ROW_LIMIT, signal),
  });
}

export function myTablesQuery() {
  return queryOptions({
    queryKey: ['trpg', 'tables', 'mine', { limit: ROW_LIMIT }],
    queryFn: ({ signal }) => fetchMyTables(ROW_LIMIT, signal),
  });
}

export function myConversationsQuery() {
  return queryOptions({
    queryKey: ['chat', 'conversations', 'mine', { limit: ROW_LIMIT }],
    queryFn: ({ signal }) => fetchMyConversations(ROW_LIMIT, signal),
  });
}
