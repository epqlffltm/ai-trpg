// web/apps/web/src/pages/story/storyQueries.ts
// story(D) 가 읽는 것의 열쇠. 모두 ['story', …] 아래다. 세션 하나의 열쇠는 내 세션의 목록과 다르게 둔다(목록을 다시 읽을 때 세션까지 읽지 않는다).

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { isClientError } from '../../api/http';
import { fetchStoryModels, fetchStorySession, fetchStorySessions, SESSION_PAGE_SIZE } from '../../api/story';
import { fetchMyStoryWorlds } from '../../api/storyWorlds';

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
