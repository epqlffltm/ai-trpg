// web/apps/web/src/pages/trpg/room/useLeaveTable.ts
// 테이블에서 나가는 일(DELETE /members/me). 나가기 단추(LeaveButton)와 떠나기 전의 물음(LeaveGuard, #1344)이 함께 쓴다.
// 나간 뒤에는 이 테이블의 읽은 것을 버리고, 내 테이블과 떠난 테이블(최근 대화에 섞인다)을 다시 읽는다.
// 어디로 갈지는 부르는 쪽이 정한다. 나가기 단추는 로비로, 물음은 가려던 곳으로 간다.

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { leaveTable } from '../../../api/tableRoom';
import type { FormProblem } from '../../../auth/problem';
import { describeRoomProblem } from './roomProblem';

export type LeaveTable = {
  busy: boolean;
  problem: FormProblem | undefined;
  /** 나간다. 나갔으면 true. 그 뒤 then 을 부른다(떠나기). 읽은 것을 버리는 것은 떠난 뒤다 */
  leave: (then: () => void) => Promise<boolean>;
};

export function useLeaveTable(tableId: string): LeaveTable {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();

  const leave = useCallback(
    async (then: () => void) => {
      setBusy(true);
      setProblem(undefined);
      try {
        await leaveTable(tableId);
      } catch (error) {
        setProblem(describeRoomProblem(error));
        setBusy(false);
        return false;
      }
      // 먼저 떠난다. 방이 그려진 채로 테이블을 버리면 다시 읽어 404 를 한 번 보인다
      then();
      queryClient.removeQueries({ queryKey: ['trpg', 'tables', tableId] });
      void queryClient.invalidateQueries({ queryKey: ['trpg', 'tables'] });
      void queryClient.invalidateQueries({ queryKey: ['trpg', 'past-tables'] });
      return true;
    },
    [queryClient, tableId],
  );

  return { busy, problem, leave };
}
