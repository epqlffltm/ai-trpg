// web/apps/web/src/pages/trpg/room/LeaveGuard.tsx
// 진행 중인 테이블 방을 떠나기 전에 묻는다(#1344). 뒤로 가기, 왼쪽 메뉴, 머리의 길처럼 사이트 안에서 옮기는 것을 붙잡는다.
//   - 나가기: 나가기 단추와 같다. 자리를 비우고 걸린 서술 값을 돌려받는다. 그다음 가려던 곳으로 간다
//   - 자리 지키기: 그대로 간다. 자리는 남고 돌아와 이어 한다
//   - 닫기(Esc): 가지 않고 방에 남는다
// 탭을 닫거나 앱이 꺼지는 것은 붙잡지 못한다. 그것은 서버가 센다(연속으로 선언을 내지 않으면 값을 걸지 않고, 더 오래면 뺀다, #1345).

import { Button, Dialog } from '@ai-trpg/ui';
import { useBlocker } from 'react-router';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { shouldAsk } from './leaveGuardView';
import { useLeaveTable } from './useLeaveTable';

export function LeaveGuard({ tableId }: { tableId: string }) {
  const blocker = useBlocker(({ currentLocation, nextLocation }) => shouldAsk(tableId, currentLocation, nextLocation));
  const { busy, problem, leave } = useLeaveTable(tableId);
  const blocked = blocker.state === 'blocked';

  return (
    <Dialog title="테이블에서 나갈까요?" open={blocked} onClose={() => (blocked ? blocker.reset() : undefined)}>
      <p>나가면 자리를 비우고 걸린 서술 값을 돌려받습니다. 진행 중인 판이라 다시 들어올 수는 없습니다.</p>
      <p>자리를 지키면 그대로 앉아 있어 돌아와 이어 할 수 있습니다. 선언하지 않는 라운드가 이어지면 서술 값을 걸지 않고, 오래 비우면 자리에서 빠집니다.</p>
      <ProblemNotice problem={problem} />
      <div className="actions">
        <Button variant="secondary" disabled={busy} onClick={() => (blocked ? blocker.proceed() : undefined)}>
          자리 지키기
        </Button>
        <Button busy={busy} onClick={() => void leave(() => (blocked ? blocker.proceed() : undefined))}>
          나가기
        </Button>
      </div>
    </Dialog>
  );
}
