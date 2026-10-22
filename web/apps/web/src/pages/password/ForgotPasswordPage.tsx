// web/apps/web/src/pages/password/ForgotPasswordPage.tsx
// 비밀번호를 잊었을 때(A2). 이메일을 받아 재설정 링크를 보낸다.
// 가입된 주소든 아니든 같은 답을 보인다. 가입 여부를 알려 주지 않는다(서버도 같은 202 다).

import { Button, Notice, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { requestPasswordReset } from '../../api/password';
import { describePasswordProblem } from '../../auth/passwordProblem';
import type { FormProblem } from '../../auth/problem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { useCountdown } from '../../hooks/useCountdown';

const SENT =
  '가입된 주소라면 비밀번호를 새로 정하는 링크를 보냈습니다. 링크는 30분 동안 한 번만 쓸 수 있습니다. 메일이 오지 않으면 스팸함도 확인해 주세요.';

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const wait = useCountdown();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      await requestPasswordReset(email.trim());
      setSent(true);
    } catch (error) {
      const next = describePasswordProblem(error, 'request');
      setProblem(next);
      if (next.waitSeconds) wait.start(next.waitSeconds);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page page--narrow">
      <h1>비밀번호 찾기</h1>
      {sent ? (
        <>
          <Notice>{SENT}</Notice>
          <Link to="/login">로그인으로</Link>
        </>
      ) : (
        <form onSubmit={submit} noValidate>
          <p>가입한 이메일을 적으면 비밀번호를 새로 정하는 링크를 보냅니다.</p>
          <ProblemNotice problem={problem} />
          <TextField
            label="이메일"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            error={problem?.fields?.email}
            required
          />
          <Button type="submit" busy={busy} disabled={!email.trim() || wait.remaining > 0}>
            {wait.remaining > 0 ? `${wait.remaining}초 뒤에 다시` : '링크 받기'}
          </Button>
        </form>
      )}
    </main>
  );
}
