// web/apps/web/src/pages/trpg/room/status/useRaise.ts
// 내 캐릭터의 쌓인 점수를 능력치에 놓는다(#286). 한 번에 하나만 보낸다. 답(바뀐 테이블)으로 테이블을 바로 바꾼다.
// 다른 사람에게는 abilities_raised 이벤트가 가고, 그 창은 이벤트로 테이블을 다시 읽는다.
// 놓을 수 있는지(라운드가 선언을 받는 중, 살아 있음, 점수가 있음)는 지금 라운드를 함께 읽어 본다.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { raiseAbilities } from '../../../../api/tableRoom';
import type { TableDetail } from '../../../../api/types';
import { currentRoundQuery } from '../round/roundQueries';
import { tableQuery } from '../roomQueries';
import { canRaise, type Raises } from './growthView';
import { describeRaiseProblem, type RaiseProblem } from './raiseProblem';

export type Raising = {
  /** 지금 놓을 수 있는가 */
  enabled: boolean;
  busy: boolean;
  problem: RaiseProblem | undefined;
  /** 보낸다. 받아들여졌으면 true */
  raise: (raises: Raises) => Promise<boolean>;
  /** 창을 다시 열 때 지난 알림을 지운다 */
  reset: () => void;
};

export function useRaise(table: TableDetail, myId: string | undefined): Raising {
  const queryClient = useQueryClient();
  const round = useQuery({ ...currentRoundQuery(table.id), enabled: table.status === 'playing' });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<RaiseProblem | undefined>();
  const me = table.members.find((member) => member.user_id === myId);

  async function raise(raises: Raises): Promise<boolean> {
    if (busy) return false;
    setBusy(true);
    setProblem(undefined);
    try {
      queryClient.setQueryData(tableQuery(table.id).queryKey, await raiseAbilities(table.id, raises));
      return true;
    } catch (error) {
      const next = describeRaiseProblem(error);
      setProblem(next);
      if (next.refresh) void queryClient.invalidateQueries({ queryKey: tableQuery(table.id).queryKey });
      return false;
    } finally {
      setBusy(false);
    }
  }

  return { enabled: canRaise(table, me, round.data), busy, problem, raise, reset: () => setProblem(undefined) };
}
