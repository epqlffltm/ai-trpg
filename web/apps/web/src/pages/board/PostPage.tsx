// web/apps/web/src/pages/board/PostPage.tsx
// 글 읽기(A11, /board/posts/:postId). 로그인하지 않아도 열린다. 제목, 글쓴이, 쓴 때(고쳤으면 고친 때), 본문, 그리고 댓글.
// 본문은 글자 그대로 보인다(서식을 해석하지 않는다. 줄바꿈만 살린다). 없거나 지운 글은 404 로 알리고 게시판으로 가는 길.
// 알림(A10)의 댓글·답글 알림이 이곳으로 온다.
// 모양은 Stitch 11번: 위에 게시판 탭, 글은 한 장의 종이(머리에 게시판 표, 제목, 글쓴이·때·댓글 수, 오른쪽에 고치기·지우기·고정·신고),
// 그 아래 댓글 칸. 단추가 누구에게 보일지는 boardPermissions.ts 가 정한다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { formatDateTime } from '../../format/dateTime';
import { BoardTabs } from './BoardTabs';
import { boardsQuery, postQuery } from './boardQueries';
import { boardProblemText } from './boardProblem';
import { authorName, isEdited } from './boardView';
import { CommentList } from './CommentList';
import { PostActions } from './PostActions';
import { useBoardMe } from './useBoardMe';

export function PostPage() {
  const { postId = '' } = useParams();
  const post = useQuery(postQuery(postId));
  const boards = useQuery(boardsQuery());
  const board = boards.data?.find((item) => item.slug === post.data?.board);
  const { me } = useBoardMe();

  return (
    <main className="page board-page">
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
          <article className="post board-card" aria-labelledby="post-title">
            <header className="post__head">
              <div className="post__heading">
                <Link className="post__board" to={`/board/${encodeURIComponent(post.data.board)}`}>
                  {board?.name ?? '게시판'}
                </Link>
                <h1 id="post-title">{post.data.title}</h1>
                <p className="post__meta">
                  <strong>{authorName(post.data)}</strong> · <time dateTime={post.data.created_at}>{formatDateTime(post.data.created_at)}</time>
                  {isEdited(post.data) ? ` · 고침 ${formatDateTime(post.data.updated_at)}` : ''} · 댓글 {post.data.comment_count}
                </p>
              </div>
              <PostActions post={post.data} board={board} me={me} />
            </header>
            <div className="post__content">{post.data.content}</div>
          </article>
          <CommentList postId={post.data.id} count={post.data.comment_count} />
        </>
      ) : null}
    </main>
  );
}
