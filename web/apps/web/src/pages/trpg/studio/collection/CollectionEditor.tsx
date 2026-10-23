// web/apps/web/src/pages/trpg/studio/collection/CollectionEditor.tsx
// 묶음 재료(로어북, 몬스터 모음)의 제목과 소개 입력. 만들기와 고치기가 함께 쓴다. 보내기는 쓰는 쪽(onSubmit)이 맡는다.

import { Button, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent, type ReactNode } from 'react';
import type { FormProblem } from '../../../../auth/problem';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { TextAreaField } from '../../../../components/TextAreaField';
import { DESCRIPTION_MAX, TITLE_MAX } from '../rulebooks/rulebookForm';
import { collectionHints, type CollectionDraft } from './collectionForm';

type Props = {
  /** 폼의 이름(로어북, 몬스터 모음) */
  label: string;
  initial: CollectionDraft;
  submitLabel: string;
  busy: boolean;
  problem: FormProblem | undefined;
  onSubmit: (draft: CollectionDraft) => void;
  actions?: ReactNode;
};

export function CollectionEditor({ label, initial, submitLabel, busy, problem, onSubmit, actions }: Props) {
  const [draft, setDraft] = useState<CollectionDraft>(initial);
  const hints = collectionHints(draft);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (Object.keys(hints).length === 0) onSubmit(draft);
  }

  return (
    <form onSubmit={submit} noValidate aria-label={label}>
      <ProblemNotice problem={problem} />
      <TextField
        label="제목"
        name="title"
        maxLength={TITLE_MAX}
        value={draft.title}
        onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
        error={draft.title === '' ? undefined : hints.title}
      />
      <TextAreaField
        label="소개(선택)"
        name="description"
        rows={3}
        maxLength={DESCRIPTION_MAX}
        value={draft.description}
        onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))}
        error={hints.description}
      />
      <div className="form-actions">
        <Button type="submit" busy={busy} disabled={Object.keys(hints).length > 0}>
          {submitLabel}
        </Button>
        {actions}
      </div>
    </form>
  );
}
