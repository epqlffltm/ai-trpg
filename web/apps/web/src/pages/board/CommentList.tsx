// web/apps/web/src/pages/board/CommentList.tsx
// 글의 댓글과 답글(A11). 오래된 것부터 한 묶음씩, "댓글 더 보기"로 이어 받는다. 답글은 그 댓글 아래에 들여 둔다.
// 지운 댓글에 답글이 있으면 "삭제된 댓글입니다"로 자리만 남는다. 댓글 쓰기는 아직 없다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import type { BoardComment } from '../../api/types';
import { formatDateTime } from '../../format/dateTime';
import { commentsQuery } from './boardQueries';
import { boardProblemText } from './boardProblem';
import { authorName, commentText } from './boardView';

export function CommentList({ postId, count }: { postId: string; count: number }) {
  const comments = useInfiniteQuery(commentsQuery(postId));
  const threads = comments.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="page-section" aria-labelledby="comments-heading">
      <h2 id="comments-heading">댓글 {count}개</h2>
      {comments.isError ? (
        <Notice tone="error">
          {boardProblemText(comments.error, '댓글')}{' '}
          <Button variant="quiet" onClick={() => void (comments.data ? comments.fetchNextPage() : comments.refetch())}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {comments.isSuccess && threads.length === 0 ? <p className="hint">아직 댓글이 없습니다.</p> : null}
      <ul className="plain-list comments" aria-label="댓글">
        {threads.map((thread) => (
          <li key={thread.id}>
            <CommentBody comment={thread} />
            {thread.replies.length > 0 ? (
              <ul className="plain-list comments comments--replies" aria-label="답글">
                {thread.replies.map((reply) => (
                  <li key={reply.id}>
                    <CommentBody comment={reply} />
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        ))}
      </ul>
      {comments.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={comments.isFetchingNextPage} onClick={() => void comments.fetchNextPage()}>
            댓글 더 보기
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function CommentBody({ comment }: { comment: BoardComment }) {
  return (
    <article className={comment.deleted ? 'comment comment--deleted' : 'comment'}>
      {comment.deleted ? null : (
        <p className="hint comment__meta">
          {authorName(comment)} · <time dateTime={comment.created_at}>{formatDateTime(comment.created_at)}</time>
        </p>
      )}
      <p className="comment__text">{commentText(comment)}</p>
    </article>
  );
}
