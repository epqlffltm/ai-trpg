// web/apps/web/src/pages/story/StorySessionPage.tsx
// 장면(D2, /story/sessions/:sessionId). 로그인해야 열린다. 내 것이 아니거나 볼 수 없는 등급이면 서버는 404 다.
// 이 파일은 읽기와 상태(세션, 받는 중인 답)만 맡는다. 그리는 것은 StoryRoom 이다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { ApiError } from '../../api/errors';
import { storySessionQuery } from './storyQueries';
import { StoryRoom } from './StoryRoom';
import { useStoryTurn } from './useStoryTurn';

export function StorySessionPage() {
  const { sessionId = '' } = useParams();
  const turns = useStoryTurn(sessionId);
  const query = useQuery(storySessionQuery(sessionId));

  if (query.isPending) return <p className="page page--loading">불러오는 중</p>;
  if (query.isError) return <LoadProblem error={query.error} onRetry={() => void query.refetch()} />;
  return <StoryRoom key={sessionId} session={query.data} turns={turns} />;
}

function LoadProblem({ error, onRetry }: { error: Error; onRetry: () => void }) {
  // 경로의 ID 가 UUID 가 아니면 422 다. 없는 것과 같게 본다
  const missing = error instanceof ApiError && (error.status === 404 || error.status === 422);
  return (
    <main className="page page--narrow">
      <h1>이야기</h1>
      {missing ? (
        <Notice>볼 수 없는 세션입니다. 내 세션이 아니거나 볼 수 없는 등급입니다.</Notice>
      ) : (
        <Notice tone="error">
          세션을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={onRetry}>
            다시 시도
          </Button>
        </Notice>
      )}
      <Link to="/story">내 이야기</Link>
    </main>
  );
}
