// web/apps/web/src/pages/signup/SignupCodeStep.tsx
// 가입 2단계. 메일로 온 6자리 코드(5분)를 맞혀 가입 티켓을 받는다. 다섯 번 틀리면 그 코드는 버려진다(서버).
// 코드를 다시 받는 것은 1단계의 요청을 다시 보내는 것이다(1분에 한 통, 1시간에 다섯 통).

import { Button, Notice, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { requestSignupCode, verifySignupCode } from '../../api/signup';
import { describeSignupProblem, type SignupProblem } from '../../auth/signupProblem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { formatRemaining, secondsFromNow, useCountdown } from '../../hooks/useCountdown';

/** 코드가 유효한 시간(5분)과 다시 받기까지 기다리는 시간(1분) */
const CODE_SECONDS = 5 * 60;
const RESEND_SECONDS = 60;
const CODE_PATTERN = /^[0-9]{6}$/;

type Props = {
  email: string;
  onVerified: (ticket: string) => void;
  onChangeEmail: () => void;
};

export function SignupCodeStep({ email, onVerified, onChangeEmail }: Props) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<SignupProblem | undefined>();
  const [sent, setSent] = useState<string | undefined>();
  const codeClock = useCountdown(secondsFromNow(CODE_SECONDS));
  const resendClock = useCountdown(secondsFromNow(RESEND_SECONDS));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      onVerified(await verifySignupCode(email, code));
    } catch (error) {
      setProblem(describeSignupProblem(error, 'code'));
      setBusy(false);
    }
  }

  async function resend() {
    setProblem(undefined);
    setSent(undefined);
    try {
      await requestSignupCode(email);
      setSent('코드를 다시 보냈습니다. 메일이 오지 않으면 스팸함도 확인해 주세요.');
      setCode('');
      codeClock.start(CODE_SECONDS);
      resendClock.start(RESEND_SECONDS);
    } catch (error) {
      const next = describeSignupProblem(error, 'email');
      setProblem(next);
      if (next.waitSeconds) resendClock.start(next.waitSeconds);
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <p>
        <strong>{email}</strong> 로 6자리 코드를 보냈습니다.{' '}
        {codeClock.remaining > 0 ? `${formatRemaining(codeClock.remaining)} 안에 입력해 주세요.` : '코드가 만료됐습니다. 다시 받아 주세요.'}
      </p>
      <ProblemNotice problem={problem} />
      {sent ? <Notice>{sent}</Notice> : null}
      <TextField
        label="인증 코드"
        name="code"
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern="[0-9]{6}"
        maxLength={6}
        value={code}
        onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))}
        error={problem?.fields?.code}
        required
      />
      <div className="actions">
        <Button type="submit" busy={busy} disabled={!CODE_PATTERN.test(code) || codeClock.remaining === 0}>
          다음
        </Button>
        <Button variant="secondary" onClick={resend} disabled={resendClock.remaining > 0}>
          {resendClock.remaining > 0 ? `코드 다시 받기 (${resendClock.remaining}초)` : '코드 다시 받기'}
        </Button>
        <Button variant="quiet" onClick={onChangeEmail}>
          이메일 바꾸기
        </Button>
      </div>
    </form>
  );
}
