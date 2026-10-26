// web/apps/web/src/pages/operator/ReasonConfirm.tsx
// 사유를 적어야 하는 운영자의 동작 하나(제재, 공개 금지와 풀기). 누르면 창에서 무엇이 일어나는지 알리고 사유를 받는다.
// 사유는 감사 기록에만 남는다. 성공하면 창을 닫고 사유를 비운다. 실패하면 창을 열어 둔다.

import { useState, type ReactNode } from 'react';
import type { FormProblem } from '../../auth/problem';
import { ConfirmButton } from '../../components/ConfirmButton';
import { reasonProblem } from './moderationPure';
import { ReasonField } from './ReasonField';

type Props = {
  label: string;
  title: string;
  confirm: string;
  children: ReactNode;
  busy: boolean;
  problem: FormProblem | undefined;
  /** 다듬은 사유로 부른다. 성공했으면 true */
  onSubmit: (reason: string) => Promise<boolean>;
};

export function ReasonConfirm({ label, title, confirm, children, busy, problem, onSubmit }: Props) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | undefined>();

  async function act(): Promise<boolean> {
    const found = reasonProblem(reason) ?? undefined;
    setError(found);
    if (found) return false;
    const done = await onSubmit(reason.trim());
    if (done) setReason('');
    return done;
  }

  return (
    <ConfirmButton label={label} title={title} confirm={confirm} busy={busy} problem={problem} onConfirm={act} variant="secondary">
      {children}
      <ReasonField label="사유" value={reason} error={error} onChange={setReason} />
    </ConfirmButton>
  );
}
