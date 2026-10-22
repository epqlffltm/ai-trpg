// web/apps/web/src/pages/login/CredentialsStep.tsx
// 로그인 1단계. 아이디와 비밀번호를 보내고 티켓을 받는다. 메일로 코드가 간다.
// 시도가 너무 많으면(429) 남은 초를 세며 버튼을 막는다.

import { Button, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { startLogin } from '../../api/auth';
import { describeLoginProblem, type LoginProblem } from '../../auth/loginProblem';
import { useCountdown } from '../../hooks/useCountdown';
import { ProblemNotice } from '../../components/ProblemNotice';

type Props = {
  initialProblem?: LoginProblem | undefined;
  /** 가입을 막 마치고 왔으면 그 아이디 */
  initialUsername?: string | undefined;
  onTicket: (ticket: string) => void;
};

export function CredentialsStep({ initialProblem, initialUsername, onTicket }: Props) {
  const [username, setUsername] = useState(initialUsername ?? '');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<LoginProblem | undefined>(initialProblem);
  const wait = useCountdown();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      const challenge = await startLogin(username, password);
      onTicket(challenge.login_ticket);
    } catch (error) {
      const next = describeLoginProblem(error, 'credentials');
      setProblem(next);
      if (next.waitSeconds) wait.start(next.waitSeconds);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <ProblemNotice problem={problem} />
      <TextField
        label="아이디"
        name="username"
        autoComplete="username"
        value={username}
        onChange={(event) => setUsername(event.target.value)}
        error={problem?.fields?.username}
        required
      />
      <TextField
        label="비밀번호"
        name="password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        error={problem?.fields?.password}
        maxLength={128}
        required
      />
      <Button type="submit" busy={busy} disabled={!username || !password || wait.remaining > 0}>
        {wait.remaining > 0 ? `${wait.remaining}초 뒤에 다시` : '다음'}
      </Button>
    </form>
  );
}
