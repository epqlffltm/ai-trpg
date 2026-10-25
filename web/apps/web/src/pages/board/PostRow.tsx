// web/apps/web/src/pages/board/PostRow.tsx
// 글 목록의 한 줄. 제목(글로 가는 길), 고정 표, 글쓴이, 쓴 때, 댓글 수. 본문은 목록에 없다.

import { Link } from 'react-router';
import type { PostSummary } from '../../api/types';
import { formatDateTime } from '../../format/dateTime';
import { authorName } from './boardView';

export function PostRow({ post, boardName }: { post: PostSummary; boardName?: string | undefined }) {
  return (
    <li className={post.pinned ? 'post-row post-row--pinned' : 'post-row'}>
      <div className="post-row__title">
        {post.pinned ? <span className="post-row__pin">고정</span> : null}
        {boardName ? <span className="hint">[{boardName}]</span> : null}
        <Link to={`/board/posts/${encodeURIComponent(post.id)}`}>{post.title}</Link>
        {post.comment_count > 0 ? <span className="hint" aria-label={`댓글 ${post.comment_count}개`}>({post.comment_count})</span> : null}
      </div>
      <p className="hint post-row__meta">
        {authorName(post)} · <time dateTime={post.created_at}>{formatDateTime(post.created_at)}</time>
      </p>
    </li>
  );
}
