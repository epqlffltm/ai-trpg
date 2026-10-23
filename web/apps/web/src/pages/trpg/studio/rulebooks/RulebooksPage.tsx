// web/apps/web/src/pages/trpg/studio/rulebooks/RulebooksPage.tsx
// 내 룰북 목록(B9 제작 도구의 첫 조각, /trpg/studio/rulebooks). 최근에 만든 것부터 한 쪽씩(더 보기). 로그인해야 열린다.
// 마이페이지(A5)의 "만들기"에서 온다. 다른 재료(세계관, 로어북, 몬스터 모음)와 시나리오 조립은 이 자리에 더해 간다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { formatDate } from '../../../../format/dateTime';
import { rulebooksQuery } from './rulebookQueries';

export function RulebooksPage() {
  const query = useInfiniteQuery(rulebooksQuery());
  const rulebooks = query.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <main className="page page--medium">
      <h1>내 룰북</h1>
      <p className="hint">
        룰북은 시나리오가 쓰는 규칙입니다. 규칙은 템플릿에서 오고, 방어 규칙만 고를 수 있습니다. 룰북은 나만 봅니다.
      </p>
      <p>
        <Link to="/trpg/studio/rulebooks/new">새 룰북 만들기</Link>
      </p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? (
        <Notice tone="error">
          룰북을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && rulebooks.length === 0 ? (
        <div className="empty-state">
          <p>아직 만든 룰북이 없습니다.</p>
          <Link to="/trpg/studio/rulebooks/new">첫 룰북 만들기</Link>
        </div>
      ) : null}
      <ul className="plain-list studio-list" aria-label="룰북">
        {rulebooks.map((rulebook) => (
          <li key={rulebook.id} className="studio-list__item">
            <Link to={`/trpg/studio/rulebooks/${rulebook.id}`}>{rulebook.title}</Link>
            {rulebook.description ? <p className="studio-list__description">{rulebook.description}</p> : null}
            <p className="hint">고친 날 {formatDate(rulebook.updated_at)}</p>
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
