// web/apps/web/src/pages/trpg/tables/TableCreatePage.tsx
// 테이블 만들기(B4, /trpg/tables/new?scenario_id=). 시나리오 소개(B2)의 "테이블 만들기"에서 온다. 로그인해야 열린다.
// 이 파일은 시나리오를 읽고 상태만 맡는다. 입력은 TableCreateForm 이다.
// 고를 거리(스타팅, 캐릭터 방식, 참고 자료)는 공개 소개(GET /listings/{id})에서 읽는다. 자기 시나리오의 다른 판을 고르는 것은 제작 도구(B9)에서 한다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router';
import { ApiError } from '../../../api/errors';
import { listingQuery } from '../queries';
import { TableCreateForm } from './TableCreateForm';

export function TableCreatePage() {
  const [params] = useSearchParams();
  const scenarioId = params.get('scenario_id') ?? '';
  if (!scenarioId) return <NoScenario message="어느 시나리오로 만들지 먼저 고르세요." />;
  return <WithListing scenarioId={scenarioId} />;
}

function WithListing({ scenarioId }: { scenarioId: string }) {
  const query = useQuery(listingQuery(scenarioId, true));
  if (query.isPending) return <p className="page page--loading">불러오는 중</p>;
  if (query.isError) {
    const missing = query.error instanceof ApiError && (query.error.status === 404 || query.error.status === 422);
    if (missing) return <NoScenario message="볼 수 없는 시나리오입니다." />;
    return (
      <main className="page page--narrow">
        <h1>테이블 만들기</h1>
        <Notice tone="error">
          시나리오를 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      </main>
    );
  }
  return <TableCreateForm listing={query.data} />;
}

function NoScenario({ message }: { message: string }) {
  return (
    <main className="page page--narrow">
      <h1>테이블 만들기</h1>
      <Notice>{message}</Notice>
      <Link to="/trpg">시나리오 찾기</Link>
    </main>
  );
}
