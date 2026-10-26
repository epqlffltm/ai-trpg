// web/apps/web/src/pages/board/CommentList.tsx
// 글의 댓글과 답글(A11). 오래된 것부터 한 묶음씩, "댓글 더 보기"로 이어 받는다. 답글은 그 댓글 아래에 들여 둔다.
// 지운 댓글에 답글이 있으면 "삭제된 댓글입니다"로 자리만 남는다.
// 로그인했으면 위에 댓글 쓰기, 댓글마다 답글(답글에는 달지 못한다), 고치기(글쓴이), 지우기(글쓴이와 운영자), 신고(남의 것).
// 로그인하지 않았으면 쓰기 대신 로그인으로 가는 길(마치면 이 글로 돌아온다).

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useLocation } from 'react-router';
import type { BoardComment, BoardMe } from '../../api/types';
import { ConfirmButton } from '../../components/ConfirmButton';
import { formatDateTime } from '../../format/dateTime';
import { canDeleteComment, canEditComment, canReply, canReport } from './boardPermissions';
import { commentsQuery } from './boardQueries';
import { boardProblemText } from './boardProblem';
import { authorName, commentText, isEdited } from './boardView';
import { describeBoardWriteProblem } from './boardWriteProblem';
import { CommentForm } from './CommentForm';
import { ReportButton } from './ReportButton';
import { useBoardMe } from './useBoardMe';
import { useCreateComment, useDeleteComment, useUpdateComment } from './useCommentWrites';

export function CommentList({ postId, count }: { postId: string; count: number }) {
  const comments = useInfiniteQuery(commentsQuery(postId));
  const { signedIn, me } = useBoardMe();
  const threads = comments.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="page-section" aria-labelledby="comments-heading">
      <h2 id="comments-heading">댓글 {count}개</h2>
      {signedIn ? <NewComment postId={postId} /> : <SignInToComment />}
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
            <CommentItem postId={postId} comment={thread} me={me} />
            {thread.replies.length > 0 ? (
              <ul className="plain-list comments comments--replies" aria-label="답글">
                {thread.replies.map((reply) => (
                  <li key={reply.id}>
                    <CommentItem postId={postId} comment={reply} me={me} />
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

function SignInToComment() {
  const location = useLocation();
  return (
    <p className="hint">
      <Link to="/login" state={{ from: location.pathname + location.search }}>
        로그인
      </Link>
      하면 댓글을 쓰고 신고할 수 있습니다.
    </p>
  );
}

function NewComment({ postId }: { postId: string }) {
  const creating = useCreateComment(postId, null);
  return (
    <CommentForm
      label="댓글 쓰기"
      submitLabel="댓글 달기"
      busy={creating.isPending}
      problem={creating.error ? describeBoardWriteProblem(creating.error, '댓글') : undefined}
      onSubmit={creating.submit}
    />
  );
}

type ItemProps = { postId: string; comment: BoardComment; me: BoardMe | undefined };
type Mode = 'read' | 'edit' | 'reply';

/** 댓글 한 줄. 고치는 동안은 글 대신 폼, 답글을 쓰는 동안은 글 아래에 폼 */
function CommentItem({ postId, comment, me }: ItemProps) {
  const [mode, setMode] = useState<Mode>('read');
  const read = () => setMode('read');
  return (
    <article className={comment.deleted ? 'comment comment--deleted' : 'comment'}>
      {comment.deleted ? null : (
        <p className="hint comment__meta">
          {authorName(comment)} · <time dateTime={comment.created_at}>{formatDateTime(comment.created_at)}</time>
          {isEdited(comment) ? ' · 고침' : ''}
        </p>
      )}
      {mode === 'edit' ? <EditComment postId={postId} comment={comment} onDone={read} /> : <p className="comment__text">{commentText(comment)}</p>}
      {mode === 'read' && me !== undefined ? <CommentActions postId={postId} comment={comment} me={me} onMode={setMode} /> : null}
      {mode === 'reply' ? <ReplyComment postId={postId} parentId={comment.id} onDone={read} /> : null}
    </article>
  );
}

type ActionsProps = { postId: string; comment: BoardComment; me: BoardMe; onMode: (mode: Mode) => void };

function CommentActions({ postId, comment, me, onMode }: ActionsProps) {
  const removing = useDeleteComment(postId, comment.id);
  const who = authorName(comment);
  return (
    <div className="comment__actions">
      {canReply(comment) ? (
        <Button variant="quiet" aria-label={`${who}의 댓글에 답글`} onClick={() => onMode('reply')}>
          답글
        </Button>
      ) : null}
      {canEditComment(comment, me) ? (
        <Button variant="quiet" aria-label="내 댓글 고치기" onClick={() => onMode('edit')}>
          고치기
        </Button>
      ) : null}
      {canDeleteComment(comment, me) ? (
        <ConfirmButton
          label="지우기"
          ariaLabel={`${who}의 댓글 지우기`}
          title="댓글 지우기"
          confirm="지우기"
          busy={removing.isPending}
          problem={removing.error ? describeBoardWriteProblem(removing.error, '댓글') : undefined}
          onConfirm={removing.submit}
        >
          <p>답글이 달려 있으면 "삭제된 댓글입니다"로 자리만 남습니다.</p>
        </ConfirmButton>
      ) : null}
      {canReport(comment, me) ? <ReportButton target={{ kind: 'comment', id: comment.id }} ariaLabel={`${who}의 댓글 신고`} /> : null}
    </div>
  );
}

function EditComment({ postId, comment, onDone }: { postId: string; comment: BoardComment; onDone: () => void }) {
  const updating = useUpdateComment(postId, comment.id);
  return (
    <CommentForm
      label="댓글 고치기"
      initial={comment.content ?? ''}
      submitLabel="저장"
      busy={updating.isPending}
      problem={updating.error ? describeBoardWriteProblem(updating.error, '댓글') : undefined}
      onSubmit={(content) => (content === comment.content ? Promise.resolve(true) : updating.submit(content))}
      onCancel={onDone}
    />
  );
}

function ReplyComment({ postId, parentId, onDone }: { postId: string; parentId: string; onDone: () => void }) {
  const creating = useCreateComment(postId, parentId);
  return (
    <CommentForm
      label="답글 쓰기"
      submitLabel="답글 달기"
      busy={creating.isPending}
      problem={creating.error ? describeBoardWriteProblem(creating.error, '댓글') : undefined}
      onSubmit={creating.submit}
      onCancel={onDone}
    />
  );
}
