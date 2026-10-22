// web/apps/web/src/pages/trpg/scenario/ScenarioPage.tsx
// 시나리오 소개(B2, /trpg/scenarios/:scenarioId). 이 시나리오로 한 판을 할지 정한다.
// 로그인하지 않아도 전체이용가면 보인다(#530). 볼 수 없으면(성인용, 공개가 내려감, 지워짐) 서버는 모두 404 이고 화면도 까닭을 가르지 않는다.
// 이 파일은 읽기와 상태만 맡는다. 그리는 것은 ScenarioDetail 이다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { ApiError } from '../../../api/errors';
import { useSession } from '../../../auth/useSession';
import { listingQuery } from '../queries';
import { ScenarioDetail } from './ScenarioDetail';

export function ScenarioPage() {
  const { scenarioId = '' } = useParams();
  const signedIn = useSession() !== null;
  const query = useQuery(listingQuery(scenarioId, signedIn));

  if (query.isPending) return <p className="page page--loading">불러오는 중</p>;
  if (query.isError) return <LoadProblem error={query.error} onRetry={() => void query.refetch()} />;
  return <ScenarioDetail listing={query.data} />;
}

function LoadProblem({ error, onRetry }: { error: Error; onRetry: () => void }) {
  // 경로의 ID 가 UUID 가 아니면 422 다. 없는 것과 같게 본다
  const missing = error instanceof ApiError && (error.status === 404 || error.status === 422);
  return (
    <main className="page page--narrow">
      <h1>시나리오</h1>
      {missing ? (
        <Notice>볼 수 없는 시나리오입니다.</Notice>
      ) : (
        <Notice tone="error">
          시나리오를 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={onRetry}>
            다시 시도
          </Button>
        </Notice>
      )}
      <Link to="/trpg">다른 시나리오 찾기</Link>
    </main>
  );
}
