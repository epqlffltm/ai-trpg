// web/apps/web/src/pages/me/PasswordChangeForm.tsx
// 비밀번호 바꾸기(로그인한 상태). 다른 기기는 로그아웃되고 이 기기는 새 토큰을 받아 그대로 이어진다.
// 현재 비밀번호가 틀렸거나 새 비밀번호가 규칙에 어긋나면 그 칸에 서버의 글을 보인다. 너무 많이 틀리면 기다리게 한다(429).

import { Button, Notice, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { changePassword } from '../../api/account';
import { describePasswordChangeProblem } from '../../auth/accountProblem';
import type { FormProblem } from '../../auth/problem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { useCountdown } from '../../hooks/useCountdown';

const EMPTY = { current: '', next: '', again: '' };

export function PasswordChangeForm() {
  const [draft, setDraft] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const wait = useCountdown();
  const mismatch = draft.again !== '' && draft.next !== draft.again;
  const ready = Boolean(draft.current && draft.next && draft.again) && !mismatch;

  function update(key: keyof typeof EMPTY, value: string) {
    setDraft((current) => ({ ...current, [key]: value }));
    setDone(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      await changePassword(draft.current, draft.next);
      setDraft(EMPTY);
      setDone(true);
    } catch (error) {
      const next = describePasswordChangeProblem(error);
      setProblem(next);
      if (next.waitSeconds) wait.start(next.waitSeconds);
    }
    setBusy(false);
  }

  return (
    <section className="page-section" aria-labelledby="password-heading">
      <h2 id="password-heading">비밀번호 바꾸기</h2>
      <form onSubmit={submit} noValidate>
        {done ? <Notice>비밀번호를 바꿨습니다. 다른 기기에서는 로그아웃됐습니다.</Notice> : null}
        <ProblemNotice problem={problem} />
        <TextField
          label="현재 비밀번호"
          name="current_password"
          type="password"
          autoComplete="current-password"
          maxLength={128}
          value={draft.current}
          onChange={(event) => update('current', event.target.value)}
          error={problem?.fields?.current_password}
          required
        />
        <TextField
          label="새 비밀번호"
          name="new_password"
          type="password"
          autoComplete="new-password"
          maxLength={128}
          value={draft.next}
          onChange={(event) => update('next', event.target.value)}
          error={problem?.fields?.new_password}
          required
        />
        <TextField
          label="새 비밀번호 확인"
          name="new_password_again"
          type="password"
          autoComplete="new-password"
          maxLength={128}
          value={draft.again}
          onChange={(event) => update('again', event.target.value)}
          error={mismatch ? '비밀번호가 서로 다릅니다.' : undefined}
          required
        />
        <Button type="submit" busy={busy} disabled={!ready || wait.remaining > 0}>
          {wait.remaining > 0 ? `${wait.remaining}초 뒤에 다시` : '바꾸기'}
        </Button>
      </form>
    </section>
  );
}
