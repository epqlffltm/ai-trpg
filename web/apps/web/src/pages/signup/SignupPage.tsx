// web/apps/web/src/pages/signup/SignupPage.tsx
// 가입(A2). 세 단계다: 이메일 → 6자리 코드 → 아이디, 닉네임, 비밀번호와 동의.
// 이 화면은 단계를 잇기만 한다. 끝나면 로그인으로 보낸다(인증 서버는 가입과 로그인을 따로 한다).
// 초대 링크(/signup?invite=코드, #990)로 오면 그 코드를 3단계의 초대 코드 칸에 채운다.
// 카드 아래에는 단계와 상관없이 로그인으로 가는 길이 있다(Stitch 4).

import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import type { SignupProblem } from '../../auth/signupProblem';
import { secondsFromNow } from '../../hooks/useCountdown';
import { INVITE_PARAM } from '../me/inviteView';
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

/** 단계 막대의 이름 셋 */
const STEP_LABELS = ['이메일', '코드', '정보'];

export function SignupPage() {
  const [stage, setStage] = useState<Stage>({ step: 'email' });
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const inviteCode = params.get(INVITE_PARAM) ?? '';
  const toLogin = (state: { notice: string; username?: string }) => navigate('/login', { replace: true, state });

  return (
    <main className="page page--narrow auth-card">
      <h1>가입</h1>
      <StepBar current={STEP_NUMBER[stage.step]} />
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
          initialInviteCode={inviteCode}
          ticketEndsAt={stage.ticketEndsAt}
          onDone={(username) => toLogin({ notice: '가입했습니다. 로그인해 주세요.', username })}
          onRestart={(problem) => setStage({ step: 'email', problem })}
          onAlreadyRegistered={(problem) => toLogin({ notice: problem.message })}
        />
      ) : null}
      <p className="auth-links">
        이미 계정이 있어요? <Link to="/login">로그인</Link>
      </p>
    </main>
  );
}

/** 세 칸의 단계 막대와 "1 / 3". 지나온 칸과 지금 칸은 강조색 */
function StepBar({ current }: { current: number }) {
  return (
    <div className="signup-steps">
      <p className="step-indicator">
        {current} / {STEP_LABELS.length}
      </p>
      <ol className="signup-steps__bar">
        {STEP_LABELS.map((label, index) => (
          <li key={label} className="signup-steps__step" aria-current={index + 1 === current ? 'step' : undefined} data-done={index + 1 <= current}>
            {label}
          </li>
        ))}
      </ol>
    </div>
  );
}
