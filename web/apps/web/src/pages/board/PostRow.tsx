// web/apps/web/src/pages/board/PostRow.tsx
// 글 목록의 한 줄(Stitch 11번). 넓은 화면에서는 칸 넷(제목, 글쓴이, 쓴 때, 댓글 수)이 표처럼 서고, 좁은 화면에서는 제목 아래 한 줄로 모인다.
// 제목 칸에 고정 표와 (검색에서) 게시판 이름. 본문은 목록에 없다.
// PostListHead 는 칸의 이름 줄이다. 꾸밈이라 읽는 프로그램에는 숨긴다(줄마다 글쓴이와 때를 그대로 읽는다).

import { Link } from 'react-router';
import type { PostSummary } from '../../api/types';
import { formatDateTime } from '../../format/dateTime';
import { authorName } from './boardView';

export function PostRow({ post, boardName }: { post: PostSummary; boardName?: string | undefined }) {
  return (
    <li className={post.pinned ? 'post-row post-row--pinned' : 'post-row'}>
      <div className="post-row__title">
        {post.pinned ? <span className="post-row__pin">고정</span> : null}
        {boardName ? <span className="post-row__board">{boardName}</span> : null}
        <Link to={`/board/posts/${encodeURIComponent(post.id)}`}>{post.title}</Link>
      </div>
      <span className="post-row__author">{authorName(post)}</span>
      <time className="post-row__time" dateTime={post.created_at}>
        {formatDateTime(post.created_at)}
      </time>
      <span className="post-row__comments" aria-label={`댓글 ${post.comment_count}개`}>
        <span aria-hidden="true">댓글 </span>
        {post.comment_count}
      </span>
    </li>
  );
}

/** 넓은 화면의 칸 이름 줄. 좁은 화면에서는 CSS 가 숨긴다 */
export function PostListHead() {
  return (
    <div className="post-head" aria-hidden="true">
      <span>제목</span>
      <span>글쓴이</span>
      <span>쓴 때</span>
      <span>댓글</span>
    </div>
  );
}
