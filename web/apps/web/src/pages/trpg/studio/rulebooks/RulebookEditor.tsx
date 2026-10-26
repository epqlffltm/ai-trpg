// web/apps/web/src/pages/trpg/studio/rulebooks/RulebookEditor.tsx
// 룰북의 입력(B9). 만들기와 고치기가 함께 쓴다. 만들 때만 템플릿을 고른다.
// 보내기는 쓰는 쪽(onSubmit)이 맡는다. 이 파일은 입력과 보내기 전의 검사만 한다.

import { Button, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent, type ReactNode } from 'react';
import type { Ability, RulebookTemplates, TemplateKey } from '../../../../api/types';
import type { FormProblem } from '../../../../auth/problem';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { TextAreaField } from '../../../../components/TextAreaField';
import { ArmorFields } from './ArmorFields';
import { ResourceFields } from './ResourceFields';
import { DESCRIPTION_MAX, GM_GUIDE_MAX, rulebookHints, TITLE_MAX, withTemplate, type RulebookDraft } from './rulebookForm';
import { templateAbilities, templateDie } from './rulebookView';
import { TemplateChoice } from './TemplateChoice';

type Props = {
  initial: RulebookDraft;
  /** 만들 때만. 있으면 템플릿을 고른다 */
  templates: RulebookTemplates | null;
  /** 판정의 주사위의 면 수(세이브의 설명에 쓴다). 만들 때는 고른 템플릿의 것을 쓴다 */
  die: number | null;
  /** 수치의 최대에 쓸 능력치(#804). 만들 때는 고른 템플릿의 것을 쓴다 */
  abilities: Ability[];
  submitLabel: string;
  busy: boolean;
  problem: FormProblem | undefined;
  onSubmit: (draft: RulebookDraft) => void;
  /** 단추 줄에 더할 것(지우기) */
  actions?: ReactNode;
};

export function RulebookEditor({ initial, templates, die, abilities, submitLabel, busy, problem, onSubmit, actions }: Props) {
  const [draft, setDraft] = useState<RulebookDraft>(initial);
  const hints = rulebookHints(draft);

  function update(changes: Partial<RulebookDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  function chooseTemplate(key: TemplateKey) {
    if (templates) setDraft((current) => withTemplate(current, templates, key));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (Object.keys(hints).length === 0) onSubmit(draft);
  }

  return (
    <form onSubmit={submit} noValidate aria-label="룰북">
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
        label="진행 지침(선택)"
        name="gm_guide"
        rows={6}
        maxLength={GM_GUIDE_MAX}
        value={draft.gmGuide}
        onChange={(event) => update({ gmGuide: event.target.value })}
        error={hints.gm_guide}
        hint="서술하는 AI 만 읽는 글입니다. 앉은 사람에게는 보이지 않습니다."
      />
      {templates ? <TemplateChoice templates={templates} selected={draft.template} onChange={chooseTemplate} /> : null}
      <ArmorFields draft={draft} die={templates ? templateDie(templates, draft.template) : die} hints={hints} onChange={update} />
      <ResourceFields
        resources={draft.resources}
        abilities={templates ? templateAbilities(templates, draft.template) : abilities}
        hints={hints}
        onChange={(resources) => update({ resources })}
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
