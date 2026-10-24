// web/apps/web/src/pages/guardian/useGuardianRequest.ts
// 미성년자가 보호자에게 동의를 부탁한다(A4). 한 번에 하나만 보낸다.
//   - 보내면 내 정보의 보호자 동의를 requested 로 바꾸고, 보낸 주소를 남긴다
//   - 내 정보가 달라졌다는 실패(본인인증 전, 이미 성년, 보호자가 이미 동의함)면 내 정보를 다시 읽는다

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { requestGuardianConsent } from '../../api/guardian';
import type { Me } from '../../api/types';
import { meQuery } from '../../auth/queries';
import { describeRequestProblem, type RequestProblem } from './guardianProblem';

type State = { busy: boolean; problem: RequestProblem | null; sentTo: string | null };

export function useGuardianRequest() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<State>({ busy: false, problem: null, sentTo: null });

  function settle(email: string) {
    queryClient.setQueryData(meQuery().queryKey, (me: Me | undefined) => (me ? { ...me, guardian_consent: 'requested' as const } : me));
    setState({ busy: false, problem: null, sentTo: email });
  }

  function fail(error: unknown) {
    const problem = describeRequestProblem(error);
    setState((current) => ({ ...current, busy: false, problem }));
    if (problem.reread) void queryClient.invalidateQueries({ queryKey: meQuery().queryKey });
  }

  async function request(email: string): Promise<boolean> {
    if (state.busy) return false;
    setState((current) => ({ ...current, busy: true, problem: null }));
    try {
      await requestGuardianConsent(email);
      settle(email);
      return true;
    } catch (error) {
      fail(error);
      return false;
    }
  }

  return { ...state, request };
}
