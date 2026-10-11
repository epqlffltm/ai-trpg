// board-server/src/posts/post.response.ts

/**
 * 글을 응답의 모양으로 바꾼다. 순수한 함수들이다.
 *
 * 칸 이름은 다른 서버들처럼 밑줄로 잇는다(author_id). 글 번호는 글자로 내보낸다.
 * 글쓴이는 ID 만 내보낸다. 이 서버는 아직 글쓴이의 이름을 모른다.
 * 목록에는 본문을 싣지 않는다. 한 쪽에 본문 스무 개를 실으면 응답이 쓸데없이 커진다.
 * 댓글 수는 글의 칸이 아니다. 따로 세어서 넘겨받는다(comment-counts/).
 */

import { Post } from './post.entity.js';

/** 글 목록의 한 줄. */
export interface PostSummaryResponse {
  id: string;
  /** 글이 있는 게시판의 주소 이름(slug) */
  board: string;
  author_id: string;
  title: string;
  /** 살아 있는 댓글과 답글의 수. 지운 것은 세지 않는다 */
  comment_count: number;
  created_at: string;
  updated_at: string;
}

/** 글 하나. 목록의 한 줄에 본문이 더해진다. */
export interface PostResponse extends PostSummaryResponse {
  content: string;
}

/** 목록에 싣는 데 필요한 글의 칸들. */
export type PostSummary = Pick<
  Post,
  'id' | 'authorId' | 'title' | 'createdAt' | 'updatedAt'
>;

export function toPostSummaryResponse(
  post: PostSummary,
  boardSlug: string,
  commentCount: number,
): PostSummaryResponse {
  return {
    id: post.id,
    board: boardSlug,
    author_id: post.authorId,
    title: post.title,
    comment_count: commentCount,
    created_at: post.createdAt.toISOString(),
    updated_at: post.updatedAt.toISOString(),
  };
}

export function toPostResponse(
  post: PostSummary & Pick<Post, 'content'>,
  boardSlug: string,
  commentCount: number,
): PostResponse {
  return {
    ...toPostSummaryResponse(post, boardSlug, commentCount),
    content: post.content,
  };
}
