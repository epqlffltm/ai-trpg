// web/apps/web/src/pages/board/PostPage.tsx
// 글 읽기(A11, /board/posts/:postId). 로그인하지 않아도 열린다. 제목, 글쓴이, 쓴 때(고쳤으면 고친 때), 본문, 그리고 댓글.
// 본문은 글자 그대로 보인다(서식을 해석하지 않는다. 줄바꿈만 살린다). 없거나 지운 글은 404 로 알리고 게시판으로 가는 길.
// 알림(A10)의 댓글·답글 알림이 이곳으로 온다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { formatDateTime } from '../../format/dateTime';
import { BoardTabs } from './BoardTabs';
import { boardsQuery, postQuery } from './boardQueries';
import { boardProblemText } from './boardProblem';
import { authorName, isEdited } from './boardView';
import { CommentList } from './CommentList';

export function PostPage() {
  const { postId = '' } = useParams();
  const post = useQuery(postQuery(postId));
  const boards = useQuery(boardsQuery());
  const board = boards.data?.find((item) => item.slug === post.data?.board);

  return (
    <main className="page page--medium">
      <BoardTabs current={post.data?.board} />
      {post.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {post.isError ? (
        <Notice tone="error">
          {boardProblemText(post.error, '글')} <Link to="/board">게시판으로</Link>
          {' '}
          <Button variant="quiet" onClick={() => void post.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {post.data ? (
        <>
          <article className="post" aria-labelledby="post-title">
            <p className="hint">
              <Link to={`/board/${encodeURIComponent(post.data.board)}`}>{board?.name ?? '게시판'}</Link>
            </p>
            <h1 id="post-title">{post.data.title}</h1>
            <p className="hint">
              {authorName(post.data)} · <time dateTime={post.data.created_at}>{formatDateTime(post.data.created_at)}</time>
              {isEdited(post.data) ? ` · 고침 ${formatDateTime(post.data.updated_at)}` : ''}
            </p>
            <div className="post__content">{post.data.content}</div>
          </article>
          <CommentList postId={post.data.id} count={post.data.comment_count} />
        </>
      ) : null}
    </main>
  );
}
