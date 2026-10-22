// web/apps/web/src/pages/signup/SignupPage.tsx
// 가입(A2). 세 단계다: 이메일 → 6자리 코드 → 아이디, 닉네임, 비밀번호와 동의.
// 이 화면은 단계를 잇기만 한다. 끝나면 로그인으로 보낸다(인증 서버는 가입과 로그인을 따로 한다).

import { useState } from 'react';
import { useNavigate } from 'react-router';
import type { SignupProblem } from '../../auth/signupProblem';
import { secondsFromNow } from '../../hooks/useCountdown';
import { EmailStep } from './EmailStep';
import { ProfileStep } from './ProfileStep';
import { SignupCodeStep } from './SignupCodeStep';

/** 가입 티켓이 유효한 시간(인증 서버의 signup_ticket, 30분) */
const TICKET_SECONDS = 30 * 60;

type Stage =
  | { step: 'email'; problem?: SignupProblem }
  | { step: 'code'; email: string }
  | { step: 'profile'; ticket: string; ticketEndsAt: number };

const STEP_NUMBER: Record<Stage['step'], number> = { email: 1, code: 2, profile: 3 };

export function SignupPage() {
  const [stage, setStage] = useState<Stage>({ step: 'email' });
  const navigate = useNavigate();
  const toLogin = (state: { notice: string; username?: string }) => navigate('/login', { replace: true, state });

  return (
    <main className="page page--narrow">
      <h1>가입</h1>
      <p className="step-indicator">{STEP_NUMBER[stage.step]} / 3</p>
      {stage.step === 'email' ? (
        <EmailStep initialProblem={stage.problem} onSent={(email) => setStage({ step: 'code', email })} />
      ) : null}
      {stage.step === 'code' ? (
        <SignupCodeStep
          email={stage.email}
          onVerified={(ticket) =>
            setStage({ step: 'profile', ticket, ticketEndsAt: secondsFromNow(TICKET_SECONDS) })
          }
          onChangeEmail={() => setStage({ step: 'email' })}
        />
      ) : null}
      {stage.step === 'profile' ? (
        <ProfileStep
          ticket={stage.ticket}
          ticketEndsAt={stage.ticketEndsAt}
          onDone={(username) => toLogin({ notice: '가입했습니다. 로그인해 주세요.', username })}
          onRestart={(problem) => setStage({ step: 'email', problem })}
          onAlreadyRegistered={(problem) => toLogin({ notice: problem.message })}
        />
      ) : null}
    </main>
  );
}
