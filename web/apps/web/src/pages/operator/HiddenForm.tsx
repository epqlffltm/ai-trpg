// web/apps/web/src/pages/operator/HiddenForm.tsx
// 캐릭터를 숨기거나 숨김을 푸는 폼. 사유가 있어야 한다. 숨김이 바뀌면 서버가 주인에게 알린다.

import { Button } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import type { HiddenInput } from '../../api/types';
import { ProblemNotice } from '../../components/ProblemNotice';
import type { ModerationProblem } from './moderationProblem';
import { reasonProblem } from './moderationPure';
import { ReasonField } from './ReasonField';

type Props = {
  hidden: boolean;
  busy: boolean;
  problem: ModerationProblem | undefined;
  /** 보내고 성공했으면 true. 그때 사유를 비운다 */
  onChange: (input: HiddenInput) => Promise<boolean>;
};

export function HiddenForm({ hidden, busy, problem, onChange }: Props) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | undefined>();

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = reasonProblem(reason) ?? undefined;
    setError(found);
    if (found) return;
    if (await onChange({ hidden: !hidden, reason: reason.trim() })) setReason('');
  }

  return (
    <form className="moderation-form" onSubmit={submit} noValidate>
      <p>
        {hidden
          ? '숨겨 있습니다. 공개 목록과 남의 새 대화에서 빠지고, 주인만 씁니다.'
          : '숨기지 않았습니다. 공개로 두었으면 공개 목록에 보입니다.'}
      </p>
      <ReasonField label={hidden ? '숨김을 푸는 사유' : '숨기는 사유'} value={reason} error={error} onChange={setReason} />
      <ProblemNotice problem={problem} />
      <div className="actions">
        <Button type="submit" variant="secondary" busy={busy}>
          {hidden ? '숨김 풀기' : '숨기기'}
        </Button>
      </div>
    </form>
  );
}
