// web/apps/web/src/pages/chat/conversation/TurnNotice.tsx
// 답을 받지 못한 까닭 한 줄과 할 일(충전으로 가기, 모델 고르기). 글자 없이 실패했으면 청구하지 않았다고 알린다.

import { Button, Notice } from '@ai-trpg/ui';
import { Link } from 'react-router';
import type { TurnProblem } from './turnProblem';

type Props = { problem: TurnProblem | null; failure: string | null; onChooseModel: () => void; onClose: () => void };

export function TurnNotice({ problem, failure, onChooseModel, onClose }: Props) {
  if (!problem && !failure) return null;
  return (
    <Notice tone="error">
      {problem?.text ?? failure}{' '}
      {problem?.charge ? <Link to="/wallet/charge">충전하기</Link> : null}
      {problem?.chooseModel ? (
        <Button variant="quiet" onClick={onChooseModel}>
          모델 고르기
        </Button>
      ) : null}
      <Button variant="quiet" onClick={onClose}>
        닫기
      </Button>
    </Notice>
  );
}
