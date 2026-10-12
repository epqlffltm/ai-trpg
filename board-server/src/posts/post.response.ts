// board-server/src/posts/post.response.ts

/**
 * 글을 응답의 모양으로 바꾼다. 순수한 함수들이다.
 *
 * 칸 이름은 다른 서버들처럼 밑줄로 잇는다(author_id). 글 번호는 글자로 내보낸다.
 * 글쓴이는 ID 와 닉네임을 내보낸다. 닉네임은 글의 칸이 아니다. 따로 읽어서 넘겨받는다(authors/).
 * 목록에는 본문을 싣지 않는다. 한 쪽에 본문 스무 개를 실으면 응답이 쓸데없이 커진다.
 * 댓글 수는 글의 칸이 아니다. 따로 세어서 넘겨받는다(comment-counts/).
 * 고정되어 있는지는 지금 시각에 달려 있다. 끝나는 시각이 지난 글은 고정하지 않은 글로 내보낸다.
 */

import { Page } from './page.js';
import { isPinned, pinnedUntilOf } from './pins.policy.js';
import { Post } from './post.entity.js';

/** 글 목록의 한 줄. */
export interface PostSummaryResponse {
  id: string;
  /** 글이 있는 게시판의 주소 이름(slug) */
  board: string;
  author_id: string;
  /** 글쓴이의 닉네임. 이 서버가 이름을 모르는 사람이면 null 이다 */
  author_nickname: string | null;
  title: string;
  /** 살아 있는 댓글과 답글의 수. 지운 것은 세지 않는다 */
  comment_count: number;
  /** 지금 고정되어 있는가 */
  pinned: boolean;
  /** 고정이 끝나는 시각. 고정되어 있지 않으면 null 이다 */
  pinned_until: string | null;
  created_at: string;
  updated_at: string;
}

/** 글 하나. 목록의 한 줄에 본문이 더해진다. */
export interface PostResponse extends PostSummaryResponse {
  content: string;
}

/** 글 목록의 한 쪽. 고정한 글을 따로 싣는다. */
export interface PostListResponse extends Page<PostSummaryResponse> {
  /** 지금 고정되어 있는 글들. 나중에 고정한 것부터다. 첫 쪽에만 싣는다. items 와 total 에는 들지 않는다 */
  pinned: PostSummaryResponse[];
}

/** 목록에 싣는 데 필요한 글의 칸들. */
export type PostSummary = Pick<
  Post,
  'id' | 'authorId' | 'title' | 'pinnedUntil' | 'createdAt' | 'updatedAt'
>;

/** 글의 칸이 아니어서 따로 넘겨받는 것들. */
export interface PostContext {
  /** 글이 있는 게시판의 주소 이름 */
  boardSlug: string;
  /** 따로 센 댓글 수(comment-counts/) */
  commentCount: number;
  /** 따로 읽은 글쓴이의 닉네임(authors/). 모르면 null */
  authorNickname: string | null;
  /** 지금 시각. 고정이 끝났는지를 이것으로 본다 */
  now: Date;
}

export function toPostSummaryResponse(
  post: PostSummary,
  context: PostContext,
): PostSummaryResponse {
  return {
    id: post.id,
    board: context.boardSlug,
    author_id: post.authorId,
    author_nickname: context.authorNickname,
    title: post.title,
    comment_count: context.commentCount,
    pinned: isPinned(post, context.now),
    pinned_until: pinnedUntilOf(post, context.now)?.toISOString() ?? null,
    created_at: post.createdAt.toISOString(),
    updated_at: post.updatedAt.toISOString(),
  };
}

export function toPostResponse(
  post: PostSummary & Pick<Post, 'content'>,
  context: PostContext,
): PostResponse {
  return { ...toPostSummaryResponse(post, context), content: post.content };
}
