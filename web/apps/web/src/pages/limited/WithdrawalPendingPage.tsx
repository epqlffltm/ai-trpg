// web/apps/web/src/pages/limited/WithdrawalPendingPage.tsx
// 탈퇴 유예 중(#603). 어느 화면으로 와도 이것만 보인다(LimitedSessionGate). 지울 시각과 취소를 보인다.
// 취소하면(DELETE /me/withdrawal) /refresh 로 모든 서버에 통하는 토큰을 받는다. 그러면 원래 화면이 그 자리에 뜬다.
// 취소하지 않으려면 그대로 두면 된다. 머리의 로그아웃은 그대로 있다.

import { Button } from '@ai-trpg/ui';
import { useState } from 'react';
import { cancelWithdrawal } from '../../api/account';
import { refreshSession } from '../../api/refresh';
import { describeAccountProblem } from '../../auth/accountProblem';
import type { FormProblem } from '../../auth/problem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { formatDateTime } from '../../format/dateTime';

export function WithdrawalPendingPage({ scheduledAt }: { scheduledAt: string }) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();

  async function cancel() {
    setBusy(true);
    setProblem(undefined);
    try {
      await cancelWithdrawal();
      await refreshSession();
    } catch (error) {
      setProblem(describeAccountProblem(error));
    }
    setBusy(false);
  }

  return (
    <main className="page page--medium">
      <h1>탈퇴를 기다리는 중입니다</h1>
      <p>
        <strong>{formatDateTime(scheduledAt)}</strong>에 계정을 지웁니다. 그때까지는 다른 서비스를 쓸 수 없습니다.
      </p>
      <p>계속 쓰려면 탈퇴를 취소하세요. 취소하지 않으면 그 시각에 그대로 지워집니다.</p>
      <ProblemNotice problem={problem} />
      <Button busy={busy} onClick={cancel}>
        탈퇴 취소하기
      </Button>
    </main>
  );
}
