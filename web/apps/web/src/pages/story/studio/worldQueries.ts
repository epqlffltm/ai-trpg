// web/apps/web/src/pages/story/studio/worldQueries.ts
// 세계관 만들기(D7)가 읽는 것의 열쇠. 모두 ['story', 'studio', 'worlds'] 아래에 둔다.
// 낱개(detail) 아래에 게시 점검과 판의 목록을 둔다. 저장하면 낱개는 받은 것으로 바꾸고 점검만 다시 읽는다.
// 만들거나 지우거나 게시하면 목록과, story 의 "내 세계관"(['story', 'my-worlds'])을 무른다.

import { queryOptions } from '@tanstack/react-query';
import { fetchMyCharacters } from '../../../api/characters';
import { fetchMyStoryWorlds, fetchStoryWorld, fetchStoryWorldCheck, fetchStoryWorldVersions } from '../../../api/storyWorlds';

export const WORLDS_KEY = ['story', 'studio', 'worlds'] as const;
/** story 첫 화면의 "내 세계관으로 시작"이 읽는 열쇠(storyQueries.ts 의 myStoryWorldsQuery) */
export const MY_WORLDS_KEY = ['story', 'my-worlds'] as const;

export function worldListKey() {
  return [...WORLDS_KEY, 'list'] as const;
}

export function worldKey(worldId: string) {
  return [...WORLDS_KEY, 'detail', worldId] as const;
}

export function worldCheckKey(worldId: string) {
  return [...worldKey(worldId), 'publish-check'] as const;
}

export function worldVersionsKey(worldId: string) {
  return [...worldKey(worldId), 'versions'] as const;
}

/** 내 세계관(최근에 고친 것부터, 100 개까지) */
export function myWorldsQuery() {
  return queryOptions({ queryKey: worldListKey(), queryFn: ({ signal }) => fetchMyStoryWorlds(signal) });
}

export function worldQuery(worldId: string) {
  return queryOptions({ queryKey: worldKey(worldId), queryFn: ({ signal }) => fetchStoryWorld(worldId, signal) });
}

export function worldCheckQuery(worldId: string) {
  return queryOptions({ queryKey: worldCheckKey(worldId), queryFn: ({ signal }) => fetchStoryWorldCheck(worldId, signal) });
}

export function worldVersionsQuery(worldId: string) {
  return queryOptions({ queryKey: worldVersionsKey(worldId), queryFn: ({ signal }) => fetchStoryWorldVersions(worldId, signal) });
}

/** 인물로 고를 내 캐릭터(최근에 고친 것부터 100 개). 게시한 판이 있는 것만 쓴다 */
export function castCharactersQuery() {
  return queryOptions({
    queryKey: ['asset', 'characters', 'mine', 'world-cast'],
    queryFn: ({ signal }) => fetchMyCharacters({ limit: 100, offset: 0 }, signal),
  });
}
