// web/apps/web/src/pages/trpg/studio/scenarios/ScenarioNewPage.tsx
// 시나리오 만들기(B9, /trpg/studio/scenarios/new). 제목, 소개, 추천 서술 모델만 받고, 만들면 고치기 화면으로 가서 탭을 채운다.

import { Button, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { createScenario } from '../../../../api/scenarios';
import type { ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { TextAreaField } from '../../../../components/TextAreaField';
import { DESCRIPTION_MAX, TITLE_MAX } from '../rulebooks/rulebookForm';
import { kindText, studioPath } from '../studioKinds';
import { useSaveAsset } from '../useAssetActions';
import { CREATED_STATE } from '../useSavedNotice';
import { ModelSelect } from './ModelSelect';
import { describeScenarioSaveProblem } from './scenarioProblem';
import { newStartDraft, startHints, toStartBody, type StartDraft } from './startForm';

export function ScenarioNewPage() {
  const navigate = useNavigate();
  const saving = useSaveAsset<ScenarioDetail>('scenarios', describeScenarioSaveProblem);
  const [draft, setDraft] = useState<StartDraft>(newStartDraft);
  const hints = startHints(draft);
  const text = kindText('scenarios');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (Object.keys(hints).length > 0) return;
    const made = await saving.save(() => createScenario(toStartBody(draft)));
    if (made) navigate(studioPath('scenarios', made.id), { replace: true, state: CREATED_STATE });
  }

  return (
    <main className="page page--medium">
      <p>
        <Link to={studioPath('scenarios')}>{text.title}</Link>
      </p>
      <h1>{text.create}</h1>
      <p className="hint">제목과 추천 서술 모델만 있으면 만들 수 있습니다. 재료, 스타팅, 캐릭터는 만든 뒤에 채웁니다.</p>
      <form onSubmit={(event) => void submit(event)} noValidate aria-label="시나리오">
        <ProblemNotice problem={saving.problem} />
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
        <ModelSelect
          value={draft.narrationModel}
          onChange={(narrationModel) => setDraft((current) => ({ ...current, narrationModel }))}
          error={saving.problem?.fields?.narration_model}
        />
        <div className="form-actions">
          <Button type="submit" busy={saving.busy} disabled={Object.keys(hints).length > 0}>
            만들기
          </Button>
        </div>
      </form>
    </main>
  );
}
