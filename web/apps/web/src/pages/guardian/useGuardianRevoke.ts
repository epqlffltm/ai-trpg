// web/apps/web/src/pages/guardian/useGuardianRevoke.ts
// 보호자가 철회 링크의 글자로 동의를 철회한다(A4). 로그인과 상관없다. 두 번 보내도 서버는 200 이고, revoked 가 이번에 철회했는지다.

import { useState } from 'react';
import { revokeGuardianConsent } from '../../api/guardian';
import { describeRevokeProblem, type LinkProblem } from './guardianProblem';

type State = { busy: boolean; problem: LinkProblem | null; revoked: boolean | null };

export function useGuardianRevoke(revokeToken: string) {
  const [state, setState] = useState<State>({ busy: false, problem: null, revoked: null });

  async function revoke(): Promise<void> {
    if (state.busy || state.revoked !== null) return;
    setState({ busy: true, problem: null, revoked: null });
    try {
      const answer = await revokeGuardianConsent(revokeToken);
      setState({ busy: false, problem: null, revoked: answer.revoked });
    } catch (error) {
      setState({ busy: false, problem: describeRevokeProblem(error), revoked: null });
    }
  }

  return { ...state, revoke };
}
