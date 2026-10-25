// web/apps/web/src/pages/board/BoardListPage.tsx
// 게시판의 글 목록(A11, /board/:slug?page=). 로그인하지 않아도 열린다. 쪽 번호로 넘긴다(20 개씩).
// 첫 쪽에는 고정한 글을 맨 위에 따로 둔다(기간이 끝나면 서버가 저절로 내린다). 위에 게시판 고르기와 이 게시판에서 찾기.
// 글쓰기는 아직 없다(다음에 더한다).

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useParams, useSearchParams } from 'react-router';
import { POST_PAGE_SIZE } from '../../api/board';
import { BoardTabs } from './BoardTabs';
import { boardPostsQuery, boardsQuery } from './boardQueries';
import { boardProblemText } from './boardProblem';
import { pageCount, parsePage } from './boardView';
import { Pager } from './Pager';
import { PostRow } from './PostRow';
import { SearchForm } from './SearchForm';

export function BoardListPage() {
  const { slug = '' } = useParams();
  const [params] = useSearchParams();
  const page = parsePage(params.get('page'));
  const boards = useQuery(boardsQuery());
  const posts = useQuery(boardPostsQuery(slug, page));
  const board = boards.data?.find((item) => item.slug === slug);
  const data = posts.data;
  const hrefFor = (next: number) => `/board/${encodeURIComponent(slug)}${next > 1 ? `?page=${next}` : ''}`;

  return (
    <main className="page page--medium">
      <h1>{board?.name ?? '게시판'}</h1>
      <BoardTabs current={slug} />
      {board?.description ? <p className="hint">{board.description}</p> : null}
      <SearchForm key={slug} board={slug} />
      {posts.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {posts.isError ? (
        <Notice tone="error">
          {boardProblemText(posts.error, '목록')}{' '}
          <Button variant="quiet" onClick={() => void posts.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {data && data.pinned.length > 0 ? (
        <ul className="plain-list posts" aria-label="고정한 글">
          {data.pinned.map((post) => (
            <PostRow key={post.id} post={post} />
          ))}
        </ul>
      ) : null}
      {data && data.items.length === 0 && data.pinned.length === 0 ? <p className="empty-state">아직 글이 없습니다.</p> : null}
      {data ? (
        <ul className="plain-list posts" aria-label="글">
          {data.items.map((post) => (
            <PostRow key={post.id} post={post} />
          ))}
        </ul>
      ) : null}
      {data ? <Pager page={page} pages={pageCount(data.total, data.size || POST_PAGE_SIZE)} hrefFor={hrefFor} /> : null}
    </main>
  );
}
