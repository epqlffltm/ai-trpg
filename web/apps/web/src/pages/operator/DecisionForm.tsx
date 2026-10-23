// web/apps/web/src/pages/operator/DecisionForm.tsx
// 신고를 처리하는 폼. 받아들일지 기각할지와 사유를 고른다. 처리를 고르기 전에는 보내지 않는다(기본값을 두지 않는다).
// 무엇을 처리하는지(캐릭터의 열린 신고 전부, 신고 하나)와 받아들이면 일어나는 일은 쓰는 쪽이 말로 넘긴다.

import { Button, Radio } from '@ai-trpg/ui';
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import type { OutcomeInput, ReportOutcome } from '../../api/types';
import { ProblemNotice } from '../../components/ProblemNotice';
import type { ModerationProblem } from './moderationProblem';
import { reasonProblem } from './moderationPure';
import { ReasonField } from './ReasonField';

type Props = {
  actionedLabel: string;
  dismissedLabel: string;
  children: ReactNode;
  busy: boolean;
  problem: ModerationProblem | undefined;
  /** 보내고 성공했으면 true. 그때 폼을 비운다 */
  onDecide: (input: OutcomeInput) => Promise<boolean>;
};

export function DecisionForm({ actionedLabel, dismissedLabel, children, busy, problem, onDecide }: Props) {
  const name = useId();
  const [outcome, setOutcome] = useState<ReportOutcome | null>(null);
  const [reason, setReason] = useState('');
  const [errors, setErrors] = useState<{ outcome?: string; reason?: string }>({});

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = { outcome: outcome === null ? '처리를 골라 주세요.' : undefined, reason: reasonProblem(reason) ?? undefined };
    setErrors(found);
    if (outcome === null || found.reason) return;
    if (await onDecide({ outcome, reason: reason.trim() })) {
      setOutcome(null);
      setReason('');
    }
  }

  return (
    <form className="moderation-form" onSubmit={submit} noValidate>
      <fieldset>
        <legend>처리</legend>
        {children}
        <Radio name={name} label={actionedLabel} checked={outcome === 'actioned'} onChange={() => setOutcome('actioned')} />
        <Radio name={name} label={dismissedLabel} checked={outcome === 'dismissed'} onChange={() => setOutcome('dismissed')} />
        {errors.outcome ? <p className="ui-field__error">{errors.outcome}</p> : null}
      </fieldset>
      <ReasonField label="처리의 사유" value={reason} error={errors.reason} onChange={setReason} />
      <ProblemNotice problem={problem} />
      <div className="actions">
        <Button type="submit" busy={busy}>
          처리하기
        </Button>
      </div>
    </form>
  );
}
