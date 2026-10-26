// web/apps/web/src/pages/personas/PersonaForm.tsx
// 페르소나의 폼(C4). 이름, 호칭, 나이, 성별, 프로필 그림, 설명, 성격, 말투 예시. 이름만 꼭 적는다.
// 저장은 쓰는 쪽(만들기, 고치기)이 한다. 칸의 문제는 처음 저장을 누른 뒤부터 보인다.

import { Button, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import type { FormProblem } from '../../auth/problem';
import { ImagePicker } from '../../components/ImagePicker';
import { ProblemNotice } from '../../components/ProblemNotice';
import { TextAreaField } from '../../components/TextAreaField';
import { draftProblems, PERSONA_LIMITS, type PersonaDraft } from './personaForm';

type Props = {
  initial: PersonaDraft;
  submitLabel: string;
  busy: boolean;
  problem: FormProblem | undefined;
  onSubmit: (draft: PersonaDraft) => void;
};

export function PersonaForm({ initial, submitLabel, busy, problem, onSubmit }: Props) {
  const [draft, setDraft] = useState(initial);
  const [touched, setTouched] = useState(false);
  const problems = draftProblems(draft);
  const errorOf = (field: keyof PersonaDraft) => (touched ? (problems[field as keyof typeof problems] ?? problem?.fields?.[field]) : problem?.fields?.[field]);
  const change = (field: keyof PersonaDraft) => (value: string) => setDraft((current) => ({ ...current, [field]: value }));

  function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (Object.keys(problems).length === 0) onSubmit(draft);
  }

  return (
    <form className="persona-form" onSubmit={submit} noValidate aria-label="페르소나">
      <ProblemNotice problem={problem} />
      <TextField label="이름" name="name" maxLength={PERSONA_LIMITS.name} value={draft.name} onChange={(event) => change('name')(event.target.value)} error={errorOf('name')} />
      <TextField
        label="호칭(상대가 나를 부르는 말)"
        name="form_of_address"
        maxLength={PERSONA_LIMITS.formOfAddress}
        value={draft.formOfAddress}
        onChange={(event) => change('formOfAddress')(event.target.value)}
        error={errorOf('formOfAddress')}
      />
      <div className="ability-grid">
        <TextField label="나이" name="age" maxLength={PERSONA_LIMITS.age} value={draft.age} onChange={(event) => change('age')(event.target.value)} error={errorOf('age')} />
        <TextField label="성별" name="gender" maxLength={PERSONA_LIMITS.gender} value={draft.gender} onChange={(event) => change('gender')(event.target.value)} error={errorOf('gender')} />
      </div>
      <ImagePicker label="프로필 그림" imageId={draft.imageId} onChange={(imageId) => setDraft((current) => ({ ...current, imageId }))} hint={problem?.fields?.imageId ?? '나만 봅니다.'} />
      <LongField label="설명" field="description" draft={draft} onChange={change('description')} error={errorOf('description')} />
      <LongField label="성격" field="personality" draft={draft} onChange={change('personality')} error={errorOf('personality')} />
      <LongField label="말투 예시" field="speechExamples" draft={draft} onChange={change('speechExamples')} error={errorOf('speechExamples')} />
      <p className="hint">상대(캐릭터)가 읽는 나의 설정입니다. 대화는 시작할 때의 설정을 복사해 두므로, 고쳐도 이미 시작한 대화는 그대로입니다.</p>
      <div className="form-actions">
        <Button type="submit" busy={busy}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

type LongProps = { label: string; field: 'description' | 'personality' | 'speechExamples'; draft: PersonaDraft; onChange: (value: string) => void; error: string | undefined };

function LongField({ label, field, draft, onChange, error }: LongProps) {
  const limit = PERSONA_LIMITS[field];
  return (
    <TextAreaField
      label={label}
      rows={4}
      maxLength={limit}
      value={draft[field]}
      onChange={(event) => onChange(event.target.value)}
      error={error}
      hint={`${draft[field].length} / ${limit}자`}
    />
  );
}
