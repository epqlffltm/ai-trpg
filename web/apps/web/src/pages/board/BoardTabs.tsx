// web/apps/web/src/pages/board/BoardTabs.tsx
// 게시판 고르기. 서버가 정한 차례대로 게시판마다 링크 하나. 지금 게시판에 aria-current.
// 게시판의 목록을 읽지 못하면 아무것도 보이지 않는다(글은 그대로 읽힌다).

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { boardsQuery } from './boardQueries';

export function BoardTabs({ current }: { current: string | undefined }) {
  const boards = useQuery(boardsQuery());
  if (!boards.data) return null;
  return (
    <nav className="board-tabs" aria-label="게시판">
      {boards.data.map((board) => (
        <Link key={board.slug} to={`/board/${encodeURIComponent(board.slug)}`} aria-current={board.slug === current ? 'page' : undefined}>
          {board.name}
        </Link>
      ))}
    </nav>
  );
}
