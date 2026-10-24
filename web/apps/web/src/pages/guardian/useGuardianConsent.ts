// web/apps/web/src/pages/guardian/useGuardianConsent.ts
// 보호자가 링크의 글자와 본인확인 업체의 글자로 동의한다(A4). 로그인과 상관없다. 한 번에 하나만 보낸다.

import { useState } from 'react';
import { giveGuardianConsent } from '../../api/guardian';
import { describeConsentProblem, type LinkProblem } from './guardianProblem';

type State = { busy: boolean; problem: LinkProblem | null; done: boolean };

export function useGuardianConsent(consentToken: string) {
  const [state, setState] = useState<State>({ busy: false, problem: null, done: false });

  async function consent(identityToken: string): Promise<void> {
    if (state.busy || state.done) return;
    setState({ busy: true, problem: null, done: false });
    try {
      await giveGuardianConsent(consentToken, identityToken);
      setState({ busy: false, problem: null, done: true });
    } catch (error) {
      setState({ busy: false, problem: describeConsentProblem(error), done: false });
    }
  }

  return { ...state, consent };
}
