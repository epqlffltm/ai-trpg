// web/apps/web/src/pages/trpg/room/LeaveButton.tsx
// 테이블에서 나가기(DELETE /members/me). 한 번 더 묻는다. 방장이 나가면 가장 먼저 들어온 사람이 방장이 된다.
// 진행 중에 나가면 내 캐릭터는 이 판에서 빠진다. 나가면 테이블 목록을 버리고 로비로 간다.

import { Button, Dialog } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router';
import { leaveTable } from '../../../api/tableRoom';
import type { FormProblem } from '../../../auth/problem';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { describeRoomProblem } from './roomProblem';

export function LeaveButton({ tableId }: { tableId: string }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const close = useCallback(() => setAsking(false), []);

  async function leave() {
    setBusy(true);
    setProblem(undefined);
    try {
      await leaveTable(tableId);
      // 먼저 떠난다. 방이 그려진 채로 테이블을 버리면 다시 읽어 404 를 한 번 보인다
      navigate('/trpg/lobby', { replace: true });
      queryClient.removeQueries({ queryKey: ['trpg', 'tables', tableId] });
      void queryClient.invalidateQueries({ queryKey: ['trpg', 'tables'] });
    } catch (error) {
      setProblem(describeRoomProblem(error));
      setBusy(false);
    }
  }

  return (
    <>
      <Button variant="secondary" onClick={() => setAsking(true)}>
        나가기
      </Button>
      <Dialog title="테이블에서 나가기" open={asking} onClose={close}>
        <p>이 테이블에서 나갑니다. 방장이면 가장 먼저 들어온 사람이 방장이 됩니다. 다시 들어오려면 초대 코드나 로비로 들어옵니다.</p>
        <ProblemNotice problem={problem} />
        <div className="actions">
          <Button busy={busy} onClick={leave}>
            나가기
          </Button>
        </div>
      </Dialog>
    </>
  );
}
