// web/apps/web/src/pages/password/ResetPasswordPage.tsx
// 재설정 메일의 링크가 여는 화면(인증 서버의 PASSWORD_RESET_URL, /reset-password). 새 비밀번호를 정한다.
//
// 링크의 # 뒤(이메일과 토큰)를 처음 그릴 때 한 번 읽어 두고 주소에서 지운다. 방문 기록이나 화면 공유에 토큰이 남지 않게 한다.
// 바꾸면 모든 기기가 로그아웃된다(서버). 이 창의 로그인 상태도 비우고 로그인으로 보낸다.

import { Button, Notice, TextField } from '@ai-trpg/ui';
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { confirmPasswordReset } from '../../api/password';
import { clearSession } from '../../api/session';
import { describePasswordProblem } from '../../auth/passwordProblem';
import type { FormProblem } from '../../auth/problem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { parseResetLink } from './resetLink';

export function ResetPasswordPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [link] = useState(() => parseResetLink(location.hash));
  const [password, setPassword] = useState('');
  const [passwordAgain, setPasswordAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const mismatch = passwordAgain !== '' && password !== passwordAgain;

  useEffect(() => {
    if (location.hash) navigate({ pathname: location.pathname }, { replace: true });
  }, [location.hash, location.pathname, navigate]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!link) return;
    setBusy(true);
    setProblem(undefined);
    try {
      await confirmPasswordReset(link.email, link.token, password);
      clearSession();
      navigate('/login', {
        replace: true,
        state: { notice: '비밀번호를 바꿨습니다. 모든 기기에서 로그아웃됐습니다. 새 비밀번호로 로그인해 주세요.' },
      });
    } catch (error) {
      setProblem(describePasswordProblem(error, 'confirm'));
      setBusy(false);
    }
  }

  if (!link || problem?.restart) {
    return (
      <main className="page page--narrow">
        <h1>비밀번호 새로 정하기</h1>
        <Notice tone="error">{problem?.message ?? '링크가 온전하지 않습니다. 메일의 링크를 다시 눌러 주세요.'}</Notice>
        <Link to="/password/forgot">재설정 메일 다시 받기</Link>
      </main>
    );
  }

  return (
    <main className="page page--narrow">
      <h1>비밀번호 새로 정하기</h1>
      <form onSubmit={submit} noValidate>
        <p>{link.email} 의 비밀번호를 새로 정합니다.</p>
        <ProblemNotice problem={problem} />
        <TextField
          label="새 비밀번호"
          name="new_password"
          type="password"
          autoComplete="new-password"
          maxLength={128}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={problem?.fields?.new_password}
          required
        />
        <TextField
          label="새 비밀번호 확인"
          name="new_password_again"
          type="password"
          autoComplete="new-password"
          maxLength={128}
          value={passwordAgain}
          onChange={(event) => setPasswordAgain(event.target.value)}
          error={mismatch ? '비밀번호가 서로 다릅니다.' : undefined}
          required
        />
        <Button type="submit" busy={busy} disabled={!password || !passwordAgain || mismatch}>
          바꾸기
        </Button>
      </form>
    </main>
  );
}
