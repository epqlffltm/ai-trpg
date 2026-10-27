// web/apps/web/src/pages/home/queries.ts
// 첫 화면이 읽는 것들의 열쇠와 부르는 함수. 줄마다 열쇠가 따로라서 따로 불러오고 따로 실패한다.
// 공개 목록은 로그인했는지에 따라 내용이 다르다(로그인 전에는 전체이용가만). 그래서 열쇠에 그것을 넣는다.

import { queryOptions } from '@tanstack/react-query';
import { fetchMyConversations, fetchMyTables, fetchPublicCharacters, fetchPublicScenarios } from '../../api/lists';
import { fetchStorySessions } from '../../api/story';
import { fetchPublicWorlds } from '../../api/storyWorlds';

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

export function publicWorldsQuery(signedIn: boolean) {
  return queryOptions({
    queryKey: ['story', 'public-worlds', 'home', { signedIn, limit: ROW_LIMIT }],
    queryFn: ({ signal }) => fetchPublicWorlds({ limit: ROW_LIMIT, offset: 0 }, signal),
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

/** 내 story 세션(최근 것부터). 서버의 한 쪽을 읽고 줄에는 앞의 몇 개만 보인다. 열쇠는 내 세션의 목록 아래라 함께 다시 읽힌다 */
export function myStorySessionsQuery() {
  return queryOptions({
    queryKey: ['story', 'sessions', 'home'],
    queryFn: ({ signal }) => fetchStorySessions(0, signal),
  });
}
