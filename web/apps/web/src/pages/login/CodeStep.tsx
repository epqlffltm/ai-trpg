// web/apps/web/src/pages/login/CodeStep.tsx
// 로그인 2단계. 메일로 온 6자리 코드를 보내 토큰을 받는다. 코드를 다시 받을 수 있다(1분에 한 통).
// 티켓이 만료됐거나 쓸 수 없으면(401) 1단계로 돌려보낸다.

import { Button, Notice, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { resendLoginCode, verifyLogin } from '../../api/auth';
import { describeLoginProblem, type LoginProblem } from '../../auth/loginProblem';
import { secondsFromNow, useCountdown } from '../../hooks/useCountdown';
import { ProblemNotice } from './ProblemNotice';

/** 코드를 다시 받기까지 기다리는 시간(인증 서버의 1분에 1통) */
const RESEND_SECONDS = 60;
const CODE_PATTERN = /^[0-9]{6}$/;

type Props = {
  ticket: string;
  ticketEndsAt: number;
  onDone: () => void;
  onRestart: (problem: LoginProblem) => void;
};

export function CodeStep({ ticket, ticketEndsAt, onDone, onRestart }: Props) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<LoginProblem | undefined>();
  const [sent, setSent] = useState<string | undefined>();
  const ticketClock = useCountdown(ticketEndsAt);
  const resendClock = useCountdown(secondsFromNow(RESEND_SECONDS));
  const ticketSeconds = ticketClock.remaining;
  const resendSeconds = resendClock.remaining;

  function fail(error: unknown) {
    const next = describeLoginProblem(error, 'code');
    if (next.restart) {
      onRestart(next);
      return;
    }
    setProblem(next);
    if (next.waitSeconds) resendClock.start(next.waitSeconds);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      await verifyLogin(ticket, code);
      onDone();
    } catch (error) {
      fail(error);
      setBusy(false);
    }
  }

  async function resend() {
    setProblem(undefined);
    setSent(undefined);
    try {
      await resendLoginCode(ticket);
      setSent('코드를 다시 보냈습니다. 메일이 오지 않으면 스팸함도 확인해 주세요.');
      resendClock.start(RESEND_SECONDS);
    } catch (error) {
      fail(error);
    }
  }

  if (ticketSeconds === 0) {
    return (
      <>
        <Notice tone="error">로그인 시간이 지났습니다.</Notice>
        <Button onClick={() => onRestart({ message: '아이디와 비밀번호부터 다시 입력해 주세요.' })}>
          처음부터 다시
        </Button>
      </>
    );
  }

  return (
    <form onSubmit={submit} noValidate>
      <p>
        가입한 메일로 6자리 코드를 보냈습니다. {formatMinutes(ticketSeconds)} 안에 입력해 주세요.
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
        <Button type="submit" busy={busy} disabled={!CODE_PATTERN.test(code)}>
          로그인
        </Button>
        <Button variant="secondary" onClick={resend} disabled={resendSeconds > 0}>
          {resendSeconds > 0 ? `코드 다시 받기 (${resendSeconds}초)` : '코드 다시 받기'}
        </Button>
      </div>
    </form>
  );
}

function formatMinutes(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return minutes > 0 ? `${minutes}분 ${rest}초` : `${rest}초`;
}
