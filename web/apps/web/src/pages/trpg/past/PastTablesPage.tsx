// web/apps/web/src/pages/trpg/past/PastTablesPage.tsx
// 내가 떠난 테이블(B10, /trpg/tables/past). 로그인해야 열린다. 최근에 떠난 것부터 20 개씩 "더 보기".
// 줄마다 제목, 떠날 때의 캐릭터, 떠난 길과 때. 누르면 떠난 때까지의 이야기를 읽는다. 모집 중에 나간 테이블은 없다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { formatDateTime } from '../../../format/dateTime';
import { pastProblemText } from './pastProblem';
import { pastTablesQuery } from './pastQueries';
import { departureLabel } from './pastStory';

export function PastTablesPage() {
  const query = useInfiniteQuery(pastTablesQuery());
  const tables = query.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <main className="page page--medium">
      <h1>떠난 테이블</h1>
      <p className="hint">시작한 테이블에서 나갔거나 내보내졌거나 빠진 테이블입니다. 떠난 때까지의 이야기를 읽고 기록을 받을 수 있습니다.</p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? (
        <Notice tone="error">
          {pastProblemText(query.error)}{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && tables.length === 0 ? <p className="empty-state">떠난 테이블이 없습니다.</p> : null}
      <ul className="plain-list posts" aria-label="떠난 테이블">
        {tables.map((table) => (
          <li key={table.table_id} className="post-row">
            <Link to={`/trpg/tables/past/${table.table_id}`}>{table.title}</Link>
            <p className="hint post-row__meta">
              {table.character_name ?? '캐릭터 없음'} · {departureLabel(table.kind)} · <time dateTime={table.left_at}>{formatDateTime(table.left_at)}</time>
            </p>
          </li>
        ))}
      </ul>
      {query.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            더 보기
          </Button>
        </div>
      ) : null}
    </main>
  );
}
