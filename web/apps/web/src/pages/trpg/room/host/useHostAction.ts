// web/apps/web/src/pages/trpg/room/host/useHostAction.ts
// 방장의 동작 하나를 부르고, 돌아온 테이블로 화면을 바로 바꾼다. 실패하면 알리고, 테이블이 달라진 탓이면 다시 읽는다.
// 동작마다(내보내기, 설정 하나) 따로 쓴다. 바쁜 것과 실패는 그 동작의 것이다.

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import type { TableDetail } from '../../../../api/types';
import { tableQuery } from '../roomQueries';
import { describeHostProblem, type HostProblem } from './hostProblem';

export type HostAction = {
  busy: boolean;
  problem: HostProblem | undefined;
  /** 부르고 성공하면 바뀐 테이블을 돌려준다. 실패하면 null */
  run: (call: () => Promise<TableDetail>) => Promise<TableDetail | null>;
};

export function useHostAction(tableId: string): HostAction {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<HostProblem | undefined>();

  const run = useCallback(
    async (call: () => Promise<TableDetail>) => {
      setBusy(true);
      setProblem(undefined);
      try {
        const table = await call();
        queryClient.setQueryData(tableQuery(tableId).queryKey, table);
        return table;
      } catch (error) {
        const next = describeHostProblem(error);
        setProblem(next);
        if (next.refresh) void queryClient.invalidateQueries({ queryKey: tableQuery(tableId).queryKey });
        return null;
      } finally {
        setBusy(false);
      }
    },
    [queryClient, tableId],
  );

  return { busy, problem, run };
}
