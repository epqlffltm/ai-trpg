// web/apps/web/src/pages/operator/useModerationAction.ts
// 운영자의 동작 하나(처리, 숨기기)를 부른다. 한 번에 하나만 보낸다. 끝나면(성공이든, 이미 처리한 탓의 실패든) 신고의 목록을 다시 읽는다.
// 동작마다 따로 쓴다. 바쁜 것과 실패는 그 동작의 것이다.

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { describeModerationProblem, type ModerationProblem } from './moderationProblem';
import { REPORTS_KEY } from './moderationQueries';

export type ModerationAction = {
  busy: boolean;
  problem: ModerationProblem | undefined;
  /** 부르고 성공하면 그 결과를, 실패하면(또는 이미 보내는 중이면) null 을 돌려준다 */
  run: <T>(call: () => Promise<T>) => Promise<T | null>;
};

export function useModerationAction(): ModerationAction {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ModerationProblem | undefined>();

  async function run<T>(call: () => Promise<T>): Promise<T | null> {
    if (busy) return null;
    setBusy(true);
    setProblem(undefined);
    try {
      const result = await call();
      void queryClient.invalidateQueries({ queryKey: REPORTS_KEY });
      return result;
    } catch (error) {
      const next = describeModerationProblem(error);
      setProblem(next);
      if (next.refresh) void queryClient.invalidateQueries({ queryKey: REPORTS_KEY });
      return null;
    } finally {
      setBusy(false);
    }
  }

  return { busy, problem, run };
}
