// web/apps/web/src/pages/signup/EmailStep.tsx
// 가입 1단계. 이메일로 6자리 코드를 보낸다. 새 주소든 이미 가입된 주소든 같은 답이다(가입 여부를 알려 주지 않는다).

import { Button, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { requestSignupCode } from '../../api/signup';
import { describeSignupProblem, type SignupProblem } from '../../auth/signupProblem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { useCountdown } from '../../hooks/useCountdown';

type Props = {
  initialProblem?: SignupProblem | undefined;
  onSent: (email: string) => void;
};

export function EmailStep({ initialProblem, onSent }: Props) {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<SignupProblem | undefined>(initialProblem);
  const wait = useCountdown();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      await requestSignupCode(email.trim());
      onSent(email.trim());
    } catch (error) {
      const next = describeSignupProblem(error, 'email');
      setProblem(next);
      if (next.waitSeconds) wait.start(next.waitSeconds);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate>
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
        {wait.remaining > 0 ? `${wait.remaining}초 뒤에 다시` : '코드 받기'}
      </Button>
    </form>
  );
}
