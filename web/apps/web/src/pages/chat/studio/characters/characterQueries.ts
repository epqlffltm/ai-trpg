// web/apps/web/src/pages/chat/studio/characters/characterQueries.ts
// 캐릭터 만들기(C6)가 읽는 것의 열쇠. 모두 ['chat', 'studio', 'characters'] 아래에 둔다.
// 목록(list)과 낱개(detail)가 있고, 게시 점검과 판의 목록은 낱개 아래에 둔다.
// 저장하면 낱개는 받은 것으로 바꾸고 점검만 다시 읽는다. 게시하면 점검과 판을 다시 읽는다. 만들거나 지우면 목록을 무른다.

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { fetchCharacter, fetchCharacterCheck, fetchCharacterVersions, fetchMyCharacters } from '../../../../api/characters';

export const PAGE_SIZE = 20;

export const CHARACTERS_KEY = ['chat', 'studio', 'characters'] as const;

export function characterListKey() {
  return [...CHARACTERS_KEY, 'list'] as const;
}

export function characterKey(characterId: string) {
  return [...CHARACTERS_KEY, 'detail', characterId] as const;
}

export function checkKey(characterId: string) {
  return [...characterKey(characterId), 'publish-check'] as const;
}

export function versionsKey(characterId: string) {
  return [...characterKey(characterId), 'versions'] as const;
}

/** 다음 쪽의 offset. 다 읽었으면 undefined(더 보기를 숨긴다) */
export function nextOffset(total: number, pagesRead: number): number | undefined {
  const read = pagesRead * PAGE_SIZE;
  return read < total ? read : undefined;
}

export function myCharactersQuery() {
  return infiniteQueryOptions({
    queryKey: characterListKey(),
    queryFn: ({ pageParam, signal }) => fetchMyCharacters({ limit: PAGE_SIZE, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => nextOffset(lastPage.total, allPages.length),
  });
}

export function characterQuery(characterId: string) {
  return queryOptions({
    queryKey: characterKey(characterId),
    queryFn: ({ signal }) => fetchCharacter(characterId, signal),
  });
}

export function checkQuery(characterId: string) {
  return queryOptions({
    queryKey: checkKey(characterId),
    queryFn: ({ signal }) => fetchCharacterCheck(characterId, signal),
  });
}

export function versionsQuery(characterId: string) {
  return queryOptions({
    queryKey: versionsKey(characterId),
    queryFn: ({ signal }) => fetchCharacterVersions(characterId, signal),
  });
}
