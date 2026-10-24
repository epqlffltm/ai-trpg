// web/apps/web/src/pages/identity/useVerifyIdentity.ts
// 본인확인 업체에서 받은 글자를 인증 서버에 낸다(A3). 한 번에 하나만 보낸다.
//   - 마치면 내 정보의 본인인증 상태를 바꾸고, 토큰을 한 번 갱신한다(성인용을 보려면 adult_content 가 실린 새 토큰이 있어야 한다).
//     환영 실버와 출석이 달라지므로 결제의 읽기(지갑, 출석)를 다시 읽는다. 환영 실버는 결제 서버가 워커로 주어 조금 늦을 수 있다
//   - 만 14세 미만(403 identity_under_age)이면 서버가 계정을 막고 refresh 쿠키를 지웠다. 로그인 화면으로 보내고 이 기기의 상태를 비운다(useLeaveSignedOut)
//   - 이미 인증했다(409)면 내 정보를 다시 읽는다

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { verifyIdentity } from '../../api/identity';
import { refreshSession } from '../../api/refresh';
import type { IdentityAnswer, Me } from '../../api/types';
import { meQuery } from '../../auth/queries';
import { useLeaveSignedOut } from '../../auth/useLeaveSignedOut';
import { describeIdentityProblem } from './identityProblem';

type State = { busy: boolean; problem: string | null };

export function useVerifyIdentity() {
  const queryClient = useQueryClient();
  const leaveSignedOut = useLeaveSignedOut();
  const [state, setState] = useState<State>({ busy: false, problem: null });

  function settle(answer: IdentityAnswer) {
    queryClient.setQueryData(meQuery().queryKey, (me: Me | undefined) => (me ? { ...me, identity: answer.identity } : me));
    void refreshSession().catch(() => undefined);
    void queryClient.invalidateQueries({ queryKey: ['billing'] });
  }

  function fail(error: unknown) {
    const problem = describeIdentityProblem(error);
    if (problem.signedOut) {
      leaveSignedOut(problem.message);
      return;
    }
    setState({ busy: false, problem: problem.message });
    if (problem.verified) void queryClient.invalidateQueries({ queryKey: meQuery().queryKey });
  }

  async function verify(token: string): Promise<boolean> {
    if (state.busy) return false;
    setState({ busy: true, problem: null });
    try {
      settle(await verifyIdentity(token));
      setState({ busy: false, problem: null });
      return true;
    } catch (error) {
      fail(error);
      return false;
    }
  }

  return { ...state, verify };
}
