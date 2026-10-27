// web/apps/web/src/pages/story/storyQueries.ts
// story(D) 가 읽는 것의 열쇠. 모두 ['story', …] 아래다. 공개 세계관은 로그인했는지에 따라 내용이 달라(전에는 전체이용가만) 열쇠에 넣는다. 세션 하나의 열쇠는 내 세션의 목록과 다르게 둔다(목록을 다시 읽을 때 세션까지 읽지 않는다).

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { isClientError } from '../../api/http';
import { fetchStoryEndings, fetchStoryGallery, fetchStoryModels, fetchStorySession, fetchStorySessions, SESSION_PAGE_SIZE } from '../../api/story';
import { fetchMyStoryWorlds, fetchPublicWorld, fetchPublicWorlds } from '../../api/storyWorlds';

export const STORY_KEY = ['story'] as const;
export const STORY_SESSIONS_KEY = [...STORY_KEY, 'sessions'] as const;

export function storySessionsQuery() {
  return infiniteQueryOptions({
    queryKey: STORY_SESSIONS_KEY,
    queryFn: ({ pageParam, signal }) => fetchStorySessions(pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const read = allPages.length * SESSION_PAGE_SIZE;
      return read < lastPage.total ? read : undefined;
    },
  });
}

export function storySessionKey(id: string) {
  return [...STORY_KEY, 'session', id] as const;
}

export function storySessionQuery(id: string) {
  return queryOptions({
    queryKey: storySessionKey(id),
    queryFn: ({ signal }) => fetchStorySession(id, signal),
    retry: (count, error) => !isClientError(error) && count < 2,
  });
}

export function myStoryWorldsQuery() {
  return queryOptions({
    queryKey: [...STORY_KEY, 'my-worlds'],
    queryFn: ({ signal }) => fetchMyStoryWorlds(signal),
  });
}

/** 모델의 값은 결제 서버의 가격표를 따라 바뀐다. 1분 동안은 다시 읽지 않는다 */
export function storyModelsQuery() {
  return queryOptions({
    queryKey: [...STORY_KEY, 'models'],
    queryFn: ({ signal }) => fetchStoryModels(signal),
    staleTime: 60 * 1000,
  });
}

/** 한 쪽의 공개 세계관 수 */
export const PUBLIC_WORLD_PAGE_SIZE = 20;

export function publicWorldsQuery(signedIn: boolean) {
  return infiniteQueryOptions({
    queryKey: [...STORY_KEY, 'public-worlds', { signedIn }],
    queryFn: ({ pageParam, signal }) => fetchPublicWorlds({ limit: PUBLIC_WORLD_PAGE_SIZE, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const read = allPages.length * PUBLIC_WORLD_PAGE_SIZE;
      return read < lastPage.total ? read : undefined;
    },
  });
}

export function publicWorldQuery(worldId: string, signedIn: boolean) {
  return queryOptions({
    queryKey: [...STORY_KEY, 'public-world', worldId, { signedIn }],
    queryFn: ({ signal }) => fetchPublicWorld(worldId, signal),
    retry: (count, error) => !isClientError(error) && count < 2,
  });
}

/** 그 세계관의 내 세션(첫 쪽만). 로그인했을 때만 */
export function worldSessionsQuery(worldId: string, signedIn: boolean) {
  return queryOptions({
    queryKey: [...STORY_SESSIONS_KEY, 'world', worldId],
    queryFn: ({ signal }) => fetchStorySessions(0, signal, worldId),
    enabled: signedIn,
  });
}

/** 그 세계관에서 내가 본 엔딩. 로그인했을 때만 */
export function storyEndingsQuery(worldId: string, signedIn = true) {
  return queryOptions({
    queryKey: [...STORY_KEY, 'endings', worldId],
    queryFn: ({ signal }) => fetchStoryEndings(worldId, signal),
    enabled: signedIn,
  });
}

/** 그 세계관에서 내가 연 일러스트(갤러리의 story 탭) */
export function storyGalleryQuery(worldId: string) {
  return queryOptions({
    queryKey: [...STORY_KEY, 'gallery', worldId],
    queryFn: ({ signal }) => fetchStoryGallery(worldId, signal),
  });
}
