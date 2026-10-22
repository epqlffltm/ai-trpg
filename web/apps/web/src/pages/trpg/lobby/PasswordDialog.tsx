// web/apps/web/src/pages/trpg/lobby/PasswordDialog.tsx
// 비밀번호가 걸린 테이블에 들어갈 때 비밀번호를 받는 창. 틀렸으면 칸에 알리고, 너무 많이 틀리면(429) 기다리게 한다.
// 틀린 까닭을 자세히 말하지 않는다(서버도 "맞지 않는다"만 준다).

import { Button, Dialog, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import type { TableSummary } from '../../../api/types';
import { ProblemNotice } from '../../../components/ProblemNotice';
import type { TableProblem } from '../tables/tableProblem';

type Props = {
  table: TableSummary | null;
  busy: boolean;
  waitSeconds: number;
  problem: TableProblem | undefined;
  onClose: () => void;
  onSubmit: (password: string) => void;
};

export function PasswordDialog({ table, busy, waitSeconds, problem, onClose, onSubmit }: Props) {
  return (
    <Dialog title={table ? `${table.title}에 들어가기` : ''} open={table !== null} onClose={onClose}>
      {table ? (
        <PasswordForm key={table.id} busy={busy} waitSeconds={waitSeconds} problem={problem} onSubmit={onSubmit} />
      ) : null}
    </Dialog>
  );
}

type FormProps = Pick<Props, 'busy' | 'waitSeconds' | 'problem' | 'onSubmit'>;

function PasswordForm({ busy, waitSeconds, problem, onSubmit }: FormProps) {
  const [password, setPassword] = useState('');

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(password);
  }

  return (
    <form onSubmit={submit} noValidate>
      {problem?.fields?.password ? null : <ProblemNotice problem={problem} />}
      <TextField
        label="테이블의 비밀번호"
        name="password"
        type="password"
        autoComplete="off"
        maxLength={64}
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        error={problem?.fields?.password}
      />
      <Button type="submit" busy={busy} disabled={!password || waitSeconds > 0}>
        {waitSeconds > 0 ? `${waitSeconds}초 뒤에 다시` : '들어가기'}
      </Button>
    </form>
  );
}
