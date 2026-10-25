// web/apps/web/src/pages/board/BoardIndexPage.tsx
// 게시판(A11, /board). 서버가 정한 첫 게시판(공지)으로 바로 보낸다. 로그인하지 않아도 열린다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router';
import { boardsQuery } from './boardQueries';
import { boardProblemText } from './boardProblem';

export function BoardIndexPage() {
  const boards = useQuery(boardsQuery());
  const first = boards.data?.[0];
  if (first) return <Navigate to={`/board/${encodeURIComponent(first.slug)}`} replace />;
  return (
    <main className="page page--medium">
      <h1>게시판</h1>
      {boards.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {boards.isError ? (
        <Notice tone="error">
          {boardProblemText(boards.error, '목록')}{' '}
          <Button variant="quiet" onClick={() => void boards.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {boards.isSuccess ? <p className="empty-state">게시판이 없습니다.</p> : null}
    </main>
  );
}
