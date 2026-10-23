// web/apps/web/src/pages/trpg/studio/useSending.ts
// 보내기 하나의 상태(B9). 한 번에 하나만 보낸다. 보내는 동안 busy, 실패하면 problem.
// 성공하면 결과를, 실패하면(또는 이미 보내는 중이면) null 을 돌려준다.

import { useState } from 'react';
import type { FormProblem } from '../../../auth/problem';

type Sending = { busy: boolean; problem: FormProblem | undefined };

export function useSending() {
  const [state, setState] = useState<Sending>({ busy: false, problem: undefined });

  async function send<T>(request: () => Promise<T>, describe: (error: unknown) => FormProblem): Promise<T | null> {
    if (state.busy) return null;
    setState({ busy: true, problem: undefined });
    try {
      const result = await request();
      setState({ busy: false, problem: undefined });
      return result;
    } catch (error) {
      setState({ busy: false, problem: describe(error) });
      return null;
    }
  }

  return { ...state, send };
}
