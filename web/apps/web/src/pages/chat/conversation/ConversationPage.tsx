// web/apps/web/src/pages/chat/conversation/ConversationPage.tsx
// 대화(C3, /chat/conversations/:conversationId). 로그인해야 열린다. 내 것이 아니거나 지웠거나 볼 수 없는 등급이면 서버는 모두 404 다.
// 이 파일은 읽기와 상태(대화, 받는 중인 답)만 맡는다. 그리는 것은 ConversationRoom 이다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { ApiError } from '../../../api/errors';
import { conversationQuery } from './conversationQueries';
import { ConversationRoom } from './ConversationRoom';
import { useConversationTurn } from './useConversationTurn';

export function ConversationPage() {
  const { conversationId = '' } = useParams();
  // 답을 받는 일은 여기서 쥔다. 받는 동안에는 "쓰는 중"을 다시 묻지 않는다
  const turns = useConversationTurn(conversationId);
  const query = useQuery(conversationQuery(conversationId, turns.turn !== null));

  if (query.isPending) return <p className="page page--loading">불러오는 중</p>;
  if (query.isError) return <LoadProblem error={query.error} onRetry={() => void query.refetch()} />;
  return <ConversationRoom key={conversationId} detail={query.data} turns={turns} />;
}

function LoadProblem({ error, onRetry }: { error: Error; onRetry: () => void }) {
  // 경로의 ID 가 UUID 가 아니면 422 다. 없는 것과 같게 본다
  const missing = error instanceof ApiError && (error.status === 404 || error.status === 422);
  return (
    <main className="page page--narrow">
      <h1>대화</h1>
      {missing ? (
        <Notice>볼 수 없는 대화입니다. 지웠거나 내 대화가 아닙니다.</Notice>
      ) : (
        <Notice tone="error">
          대화를 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={onRetry}>
            다시 시도
          </Button>
        </Notice>
      )}
      <Link to="/chat">캐릭터 찾기</Link>
    </main>
  );
}
