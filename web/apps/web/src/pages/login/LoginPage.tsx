// web/apps/web/src/pages/login/LoginPage.tsx
// 로그인(A2). 두 단계다: 아이디와 비밀번호 → 메일로 온 6자리 코드.
// 이 화면은 단계를 잇기만 한다. 단계마다의 입력과 실패는 CredentialsStep, CodeStep 이 맡는다.
// 로그인이 끝나면 오던 화면으로 돌아간다(state.from). 앱 밖의 주소로는 보내지 않는다(safeReturnPath).

import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { safeReturnPath } from '../../auth/safeReturnPath';
import type { LoginProblem } from '../../auth/loginProblem';
import { secondsFromNow } from '../../hooks/useCountdown';
import { CodeStep } from './CodeStep';
import { CredentialsStep } from './CredentialsStep';

/** 로그인 티켓이 유효한 시간(인증 서버의 login_ticket, 10분) */
const TICKET_SECONDS = 10 * 60;

type Stage = { step: 'credentials'; problem?: LoginProblem } | { step: 'code'; ticket: string; ticketEndsAt: number };

export function LoginPage() {
  const [stage, setStage] = useState<Stage>({ step: 'credentials' });
  const navigate = useNavigate();
  const location = useLocation();
  const returnPath = safeReturnPath((location.state as { from?: unknown } | null)?.from);

  return (
    <main className="page page--narrow">
      <h1>로그인</h1>
      {stage.step === 'credentials' ? (
        <CredentialsStep
          initialProblem={stage.problem}
          onTicket={(ticket) => setStage({ step: 'code', ticket, ticketEndsAt: secondsFromNow(TICKET_SECONDS) })}
        />
      ) : (
        <CodeStep
          ticket={stage.ticket}
          ticketEndsAt={stage.ticketEndsAt}
          onDone={() => navigate(returnPath, { replace: true })}
          onRestart={(problem) => setStage({ step: 'credentials', problem })}
        />
      )}
    </main>
  );
}
