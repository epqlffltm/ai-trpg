// web/apps/web/src/pages/chat/chatQueries.ts
// 캐릭터 탐색(C1)과 소개(C2)가 읽는 것. 공개 목록은 로그인했는지에 따라 내용이 달라(로그인 전에는 전체이용가만) 열쇠에 넣는다.
// 캐릭터 하나의 판은 갤러리(C7)와 같은 열쇠(publicCharacterQuery)를 쓴다. 한 번 읽은 판을 두 화면이 함께 쓴다.

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { CHARACTER_PAGE_SIZE, CONVERSATION_PAGE_SIZE, fetchConversationsWith, fetchPublicCharacterPage, fetchUnlocksOf } from '../../api/chatCharacters';

export function characterBrowseQuery(signedIn: boolean) {
  return infiniteQueryOptions({
    queryKey: ['chat', 'characters', 'browse', { signedIn }],
    queryFn: ({ pageParam, signal }) => fetchPublicCharacterPage(pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) => nextOffset(pages.length, CHARACTER_PAGE_SIZE, lastPage.total),
  });
}

/** 이 캐릭터와의 내 대화. 대화를 시작하면 ['chat', 'conversations'] 아래를 모두 다시 읽는다 */
export function conversationsWithQuery(characterId: string) {
  return infiniteQueryOptions({
    queryKey: ['chat', 'conversations', 'character', characterId],
    queryFn: ({ pageParam, signal }) => fetchConversationsWith(characterId, pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) => nextOffset(pages.length, CONVERSATION_PAGE_SIZE, lastPage.total),
  });
}

/** 이 캐릭터에서 내가 연 장면. 갤러리의 열쇠(['chat', 'gallery']) 아래에 둔다 */
export function unlocksOfQuery(characterId: string) {
  return queryOptions({
    queryKey: ['chat', 'gallery', 'character', characterId],
    queryFn: ({ signal }) => fetchUnlocksOf(characterId, signal),
  });
}

/** 다음 쪽의 offset. 다 읽었으면 undefined */
export function nextOffset(pagesRead: number, pageSize: number, total: number): number | undefined {
  const read = pagesRead * pageSize;
  return read < total ? read : undefined;
}
