// web/apps/web/src/auth/StepUpForm.tsx
// 본인 확인 창의 안(F5). 열리면 가입한 메일로 코드를 한 번 보내고, 받은 6자리 코드로 이 세션의 창을 연다.
//   - 앞서 보낸 코드를 아직 쓸 수 있으면 서버가 새로 보내지 않는다(sent: false). 그 코드를 넣으면 된다
//   - 코드는 다시 받을 수 있다(1분에 한 통). 너무 자주 받으려 하면 기다릴 초를 센다
//   - 메일을 받을 수 없으면 고객센터로 가는 길을 보인다

import { Button, Notice, TextField } from '@ai-trpg/ui';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { sendStepUpCode, verifyStepUp } from '../api/stepUp';
import { ProblemNotice } from '../components/ProblemNotice';
import { useCountdown } from '../hooks/useCountdown';
import type { FormProblem } from './problem';
import { describeStepUpProblem } from './stepUpProblem';

/** 코드를 다시 받기까지 기다리는 시간(인증 서버의 1분에 1통) */
const RESEND_SECONDS = 60;
const CODE_PATTERN = /^[0-9]{6}$/;

type Props = { onDone: () => void; onCancel: () => void };

export function StepUpForm({ onDone, onCancel }: Props) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const [sent, setSent] = useState<string | undefined>();
  const resendClock = useCountdown();
  const asked = useRef(false);

  function fail(error: unknown) {
    const next = describeStepUpProblem(error);
    setProblem(next);
    if (next.waitSeconds) resendClock.start(next.waitSeconds);
  }

  async function requestCode() {
    setProblem(undefined);
    setSent(undefined);
    try {
      const answer = await sendStepUpCode();
      setSent(answer.sent ? '가입한 메일로 6자리 코드를 보냈습니다. 메일이 오지 않으면 스팸함도 확인해 주세요.' : answer.detail);
      resendClock.start(RESEND_SECONDS);
    } catch (error) {
      fail(error);
    }
  }

  // 열릴 때 한 번 보낸다. 개발 빌드의 StrictMode 가 효과를 두 번 돌려도 한 번만 보낸다
  useEffect(() => {
    if (asked.current) return;
    asked.current = true;
    void requestCode();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 처음 열 때 한 번만 보낸다
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      await verifyStepUp(code);
      onDone();
    } catch (error) {
      fail(error);
      setBusy(false);
    }
  }

  const resendSeconds = resendClock.remaining;
  return (
    <form onSubmit={submit} noValidate>
      <p>결제와 카드를 지키려고 한 번 더 확인합니다. 확인하면 10분 동안 다시 묻지 않습니다.</p>
      {sent ? <Notice>{sent}</Notice> : null}
      <ProblemNotice problem={problem} />
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
          확인
        </Button>
        <Button variant="secondary" onClick={() => void requestCode()} disabled={resendSeconds > 0}>
          {resendSeconds > 0 ? `코드 다시 받기 (${resendSeconds}초)` : '코드 다시 받기'}
        </Button>
        <Button variant="quiet" onClick={onCancel}>
          그만두기
        </Button>
      </div>
      <p className="hint">
        가입한 메일을 더 쓸 수 없으면 <Link to="/support">고객센터</Link>로 알려 주세요.
      </p>
    </form>
  );
}
