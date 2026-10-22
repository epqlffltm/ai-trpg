// web/apps/web/src/pages/login/LoginPage.tsx
// 로그인(A2). 두 단계다: 아이디와 비밀번호 → 메일로 온 6자리 코드.
// 이 화면은 단계를 잇기만 한다. 단계마다의 입력과 실패는 CredentialsStep, CodeStep 이 맡는다.
// 로그인이 끝나면 오던 화면으로 돌아간다(state.from). 앱 밖의 주소로는 보내지 않는다(safeReturnPath).
// 가입이나 비밀번호 재설정을 마치고 오면 그 안내(state.notice)를 보이고 아이디를 채워 둔다(state.username).

import { Notice } from '@ai-trpg/ui';
import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { safeReturnPath } from '../../auth/safeReturnPath';
import type { LoginProblem } from '../../auth/loginProblem';
import { secondsFromNow } from '../../hooks/useCountdown';
import { CodeStep } from './CodeStep';
import { CredentialsStep } from './CredentialsStep';

/** 로그인 티켓이 유효한 시간(인증 서버의 login_ticket, 10분) */
const TICKET_SECONDS = 10 * 60;

type Stage = { step: 'credentials'; problem?: LoginProblem } | { step: 'code'; ticket: string; ticketEndsAt: number };

/** 다른 화면이 넘긴 것. 모르는 값은 버린다 */
type LoginState = { from?: unknown; notice?: unknown; username?: unknown } | null;

function textOf(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined;
}

export function LoginPage() {
  const [stage, setStage] = useState<Stage>({ step: 'credentials' });
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as LoginState;
  const returnPath = safeReturnPath(state?.from);
  const notice = textOf(state?.notice);

  return (
    <main className="page page--narrow">
      <h1>로그인</h1>
      {notice && stage.step === 'credentials' && !stage.problem ? <Notice>{notice}</Notice> : null}
      {stage.step === 'credentials' ? (
        <>
          <CredentialsStep
            initialProblem={stage.problem}
            initialUsername={textOf(state?.username)}
            onTicket={(ticket) => setStage({ step: 'code', ticket, ticketEndsAt: secondsFromNow(TICKET_SECONDS) })}
          />
          <p className="auth-links">
            <Link to="/signup">처음이면 가입하기</Link>
            <Link to="/password/forgot">비밀번호를 잊었어요</Link>
          </p>
        </>
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
