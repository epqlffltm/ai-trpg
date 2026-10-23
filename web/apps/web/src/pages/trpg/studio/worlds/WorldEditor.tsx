// web/apps/web/src/pages/trpg/studio/worlds/WorldEditor.tsx
// 세계관의 입력(B9). 만들기와 고치기가 함께 쓴다. 보내기는 쓰는 쪽(onSubmit)이 맡는다.
// 설정은 서술하는 AI 가 읽는 글, GM 메모는 AI 만 읽고 테이블에 앉은 사람에게 가지 않는 글이라고 칸마다 알린다.

import { Button, Checkbox, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent, type ReactNode } from 'react';
import type { FormProblem } from '../../../../auth/problem';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { TextAreaField } from '../../../../components/TextAreaField';
import { DESCRIPTION_MAX, TITLE_MAX } from '../rulebooks/rulebookForm';
import { GM_NOTES_MAX, SETTING_MAX, worldHints, type WorldDraft } from './worldForm';

type Props = {
  initial: WorldDraft;
  submitLabel: string;
  busy: boolean;
  problem: FormProblem | undefined;
  onSubmit: (draft: WorldDraft) => void;
  /** 단추 줄에 더할 것(지우기) */
  actions?: ReactNode;
};

export function WorldEditor({ initial, submitLabel, busy, problem, onSubmit, actions }: Props) {
  const [draft, setDraft] = useState<WorldDraft>(initial);
  const hints = worldHints(draft);

  function update(changes: Partial<WorldDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (Object.keys(hints).length === 0) onSubmit(draft);
  }

  return (
    <form onSubmit={submit} noValidate aria-label="세계관">
      <ProblemNotice problem={problem} />
      <TextField
        label="제목"
        name="title"
        maxLength={TITLE_MAX}
        value={draft.title}
        onChange={(event) => update({ title: event.target.value })}
        error={draft.title === '' ? undefined : hints.title}
      />
      <TextAreaField
        label="소개(선택)"
        name="description"
        rows={3}
        maxLength={DESCRIPTION_MAX}
        value={draft.description}
        onChange={(event) => update({ description: event.target.value })}
        error={hints.description}
      />
      <TextAreaField
        label="설정(선택)"
        name="setting"
        rows={10}
        maxLength={SETTING_MAX}
        value={draft.setting}
        onChange={(event) => update({ setting: event.target.value })}
        error={hints.setting}
        hint={`서술하는 AI 가 늘 읽는 배경입니다. ${draft.setting.length.toLocaleString('ko-KR')} / ${SETTING_MAX.toLocaleString('ko-KR')}자`}
      />
      <TextAreaField
        label="GM 메모(선택)"
        name="gm_notes"
        rows={5}
        maxLength={GM_NOTES_MAX}
        value={draft.gmNotes}
        onChange={(event) => update({ gmNotes: event.target.value })}
        error={hints.gm_notes}
        hint="AI 만 읽는 비밀입니다(진상, 흑막). 앉은 사람에게는 보이지 않습니다."
      />
      <Checkbox
        label="참고 자료를 켤 수 있게 하기"
        description="방장이 바깥 자료(SRD 같은 것)를 서술에 함께 쓰게 할 수 있습니다. 이 세계관에 맞지 않는 자료라면 꺼 두세요."
        checked={draft.referencesAllowed}
        onChange={(event) => update({ referencesAllowed: event.target.checked })}
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
