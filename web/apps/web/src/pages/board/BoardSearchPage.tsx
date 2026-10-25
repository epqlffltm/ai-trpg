// web/apps/web/src/pages/board/BoardSearchPage.tsx
// 글 검색(A11, /board/search?q=&board=&page=). 로그인하지 않아도 열린다. 제목과 본문에서 모든 낱말이 들어 있는 글, 새 글부터.
// board 가 있으면 그 게시판에서만, 없으면 모든 게시판에서. 검색어가 규칙에 맞지 않으면 부르지 않고 까닭을 적는다.
// 3초를 넘기면 서버가 멈춘다(503). 낱말을 줄이거나 게시판을 고르라고 알린다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router';
import { POST_PAGE_SIZE } from '../../api/board';
import { BoardTabs } from './BoardTabs';
import { boardsQuery, searchQuery } from './boardQueries';
import { boardProblemText } from './boardProblem';
import { normalizeQuery, pageCount, parsePage, searchHint, searchPath } from './boardView';
import { Pager } from './Pager';
import { PostRow } from './PostRow';
import { SearchForm } from './SearchForm';

export function BoardSearchPage() {
  const [params] = useSearchParams();
  const q = normalizeQuery(params.get('q') ?? '');
  const board = params.get('board') || undefined;
  const page = parsePage(params.get('page'));
  const hint = searchHint(q);
  const ready = q !== '' && hint === null;
  const boards = useQuery(boardsQuery());
  const results = useQuery({ ...searchQuery(q, board, page), enabled: ready });
  const boardName = (slug: string) => boards.data?.find((item) => item.slug === slug)?.name;
  const scope = board ? (boardName(board) ?? board) : '모든 게시판';
  const data = ready ? results.data : undefined;

  return (
    <main className="page page--medium">
      <h1>글 검색</h1>
      <BoardTabs current={undefined} />
      <SearchForm key={`${q}:${board ?? ''}`} initial={q} board={board} />
      <p className="hint">
        찾는 곳: {scope}
        {board ? (
          <>
            {' · '}
            <Link to={searchPath(q)}>모든 게시판에서 찾기</Link>
          </>
        ) : null}
      </p>
      {hint ? <Notice tone="error">{hint}</Notice> : null}
      {ready && results.isPending ? <p aria-busy="true">찾는 중</p> : null}
      {ready && results.isError ? (
        <Notice tone="error">
          {boardProblemText(results.error, '검색')}{' '}
          <Button variant="quiet" onClick={() => void results.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {data ? <p className="hint">찾은 글 {data.total}개</p> : null}
      {data && data.items.length === 0 ? <p className="empty-state">찾은 글이 없습니다. 다른 낱말로 찾아 보세요.</p> : null}
      {data ? (
        <ul className="plain-list posts" aria-label="찾은 글">
          {data.items.map((post) => (
            <PostRow key={post.id} post={post} boardName={board ? undefined : boardName(post.board)} />
          ))}
        </ul>
      ) : null}
      {data ? <Pager page={page} pages={pageCount(data.total, data.size || POST_PAGE_SIZE)} hrefFor={(next) => `${searchPath(q, board)}${next > 1 ? `&page=${next}` : ''}`} /> : null}
    </main>
  );
}
