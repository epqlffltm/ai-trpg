// web/apps/web/src/pages/trpg/room/LeaveButton.tsx
// 테이블에서 나가기(DELETE /members/me). 한 번 더 묻는다. 방장이 나가면 가장 먼저 들어온 사람이 방장이 된다.
// 진행 중에 나가면 내 캐릭터는 이 판에서 빠진다. 나가면 로비로 간다.
// 로비로 가는 길에 떠나기 전의 물음(LeaveGuard)이 다시 묻지 않게 이미 나갔다고 알린다(LEFT_TABLE).

import { Button, Dialog } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { LEFT_TABLE } from './leaveGuardView';
import { useLeaveTable } from './useLeaveTable';

export function LeaveButton({ tableId }: { tableId: string }) {
  const [asking, setAsking] = useState(false);
  const navigate = useNavigate();
  const { busy, problem, leave } = useLeaveTable(tableId);
  const close = useCallback(() => setAsking(false), []);

  return (
    <>
      <Button variant="secondary" onClick={() => setAsking(true)}>
        나가기
      </Button>
      <Dialog title="테이블에서 나가기" open={asking} onClose={close}>
        <p>이 테이블에서 나갑니다. 방장이면 가장 먼저 들어온 사람이 방장이 됩니다. 다시 들어오려면 초대 코드나 로비로 들어옵니다.</p>
        <ProblemNotice problem={problem} />
        <div className="actions">
          <Button busy={busy} onClick={() => void leave(() => navigate('/trpg/lobby', { replace: true, state: LEFT_TABLE }))}>
            나가기
          </Button>
        </div>
      </Dialog>
    </>
  );
}
