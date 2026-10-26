// web/apps/web/src/pages/board/boardQueries.ts
// 공지·게시판(A11)이 읽는 것의 열쇠와 부르는 함수. 게시판의 목록은 거의 바뀌지 않아 5분 동안 다시 읽지 않는다.
// 글과 목록은 화면에 올 때 읽는다(앱의 기본). 실시간으로 밀어 주지 않는다. 나(/board/me)는 로그인했을 때만 읽는다(로그아웃은 저장소를 비운다).

import { infiniteQueryOptions, keepPreviousData, queryOptions } from '@tanstack/react-query';
import { fetchBoardMe, fetchBoardPosts, fetchBoards, fetchComments, fetchPost, searchPosts } from '../../api/board';

export const BOARD_KEY = ['board'] as const;

export function boardsQuery() {
  return queryOptions({
    queryKey: [...BOARD_KEY, 'boards'],
    queryFn: ({ signal }) => fetchBoards(signal),
    staleTime: 5 * 60 * 1000,
  });
}

/** 게시판의 한 쪽. 쪽을 넘기는 동안 앞 쪽을 그대로 보인다 */
export function boardPostsQuery(slug: string, page: number) {
  return queryOptions({
    queryKey: [...BOARD_KEY, 'posts', slug, page],
    queryFn: ({ signal }) => fetchBoardPosts(slug, page, signal),
    placeholderData: keepPreviousData,
  });
}

export function postQuery(id: string) {
  return queryOptions({
    queryKey: [...BOARD_KEY, 'post', id],
    queryFn: ({ signal }) => fetchPost(id, signal),
  });
}

/** 글의 댓글. 묶음씩 "더 보기". 다음 묶음은 앞 묶음의 next 로 읽고, null 이면 끝이다 */
export function commentsQuery(postId: string) {
  return infiniteQueryOptions({
    queryKey: [...BOARD_KEY, 'comments', postId],
    queryFn: ({ pageParam, signal }) => fetchComments(postId, pageParam, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next ?? undefined,
  });
}

/** 검색의 한 쪽. 검색어가 규칙에 맞을 때만 부른다(boardView.ts 의 searchHint) */
export function searchQuery(q: string, board: string | undefined, page: number) {
  return queryOptions({
    queryKey: [...BOARD_KEY, 'search', q, board ?? '', page],
    queryFn: ({ signal }) => searchPosts(q, board, page, signal),
    placeholderData: keepPreviousData,
  });
}

/** 이 서버가 아는 나. 운영자인지는 운영 중에 바뀔 수 있어 오래 두지 않는다(앱의 기본) */
export function boardMeQuery(signedIn: boolean) {
  return queryOptions({
    queryKey: [...BOARD_KEY, 'me'],
    queryFn: ({ signal }) => fetchBoardMe(signal),
    enabled: signedIn,
  });
}
