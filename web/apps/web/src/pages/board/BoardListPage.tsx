// web/apps/web/src/pages/board/BoardListPage.tsx
// 게시판의 글 목록(A11, /board/:slug?page=). 로그인하지 않아도 열린다. 쪽 번호로 넘긴다(20 개씩).
// 첫 쪽에는 고정한 글을 맨 위에 따로 둔다(기간이 끝나면 서버가 저절로 내린다). 위에 게시판 고르기와 이 게시판에서 찾기.
// 글쓰기는 누구나 쓰는 게시판이면 늘 보인다(로그인 전이면 누르면 로그인으로). 운영자만 쓰는 게시판은 운영자에게만 보인다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams, useSearchParams } from 'react-router';
import { POST_PAGE_SIZE } from '../../api/board';
import { BoardTabs } from './BoardTabs';
import { boardPostsQuery, boardsQuery } from './boardQueries';
import { boardProblemText } from './boardProblem';
import { canWritePost } from './boardPermissions';
import { pageCount, parsePage } from './boardView';
import { Pager } from './Pager';
import { PostRow } from './PostRow';
import { SearchForm } from './SearchForm';
import { useBoardMe } from './useBoardMe';

export function BoardListPage() {
  const { slug = '' } = useParams();
  const [params] = useSearchParams();
  const page = parsePage(params.get('page'));
  const boards = useQuery(boardsQuery());
  const posts = useQuery(boardPostsQuery(slug, page));
  const board = boards.data?.find((item) => item.slug === slug);
  const { me } = useBoardMe();
  const writable = canWritePost(board, me);
  const newPath = `/board/${encodeURIComponent(slug)}/new`;
  const data = posts.data;
  const hrefFor = (next: number) => `/board/${encodeURIComponent(slug)}${next > 1 ? `?page=${next}` : ''}`;

  return (
    <main className="page page--medium">
      <h1>{board?.name ?? '게시판'}</h1>
      <BoardTabs current={slug} />
      {board?.description ? <p className="hint">{board.description}</p> : null}
      {writable ? (
        <p className="board-write">
          <Link className="ui-button ui-button--primary" to={newPath}>
            글쓰기
          </Link>
        </p>
      ) : null}
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
      {data && data.items.length === 0 && data.pinned.length === 0 ? <p className="empty-state">아직 글이 없습니다.{writable ? ' 첫 글을 써 보세요.' : ''}</p> : null}
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
