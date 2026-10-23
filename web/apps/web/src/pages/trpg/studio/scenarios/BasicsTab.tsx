// web/apps/web/src/pages/trpg/studio/scenarios/BasicsTab.tsx
// 시나리오의 기본 탭(B9): 제목, 소개, 등급, 추천 서술 모델, 서술 문체, 시계. 지우기도 여기에 둔다.
// 추천 모델이 서비스를 마치거나 쓸 수 없게 되면 위에 알린다(narration_model_status).

import { Notice, SelectField, TextField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { NarrationStyle, Rating, ScenarioDetail } from '../../../../api/types';
import { TextAreaField } from '../../../../components/TextAreaField';
import { NARRATION_STYLE_VALUES, narrationStyleLabel } from '../../labels';
import { narrationModelsQuery } from '../../queries';
import { DeleteAssetButton } from '../DeleteAssetButton';
import { DESCRIPTION_MAX, TITLE_MAX } from '../rulebooks/rulebookForm';
import { basicsDraft, basicsHints, modelStatusText, toBasicsBody, type BasicsDraft } from './basicsForm';
import { ModelSelect } from './ModelSelect';
import { ScenarioForm } from './ScenarioForm';
import { useScenarioSave } from './useScenarioSave';

const RATINGS: Record<Rating, string> = { all: '전체 이용가', adult: '성인용' };

export function BasicsTab({ scenario }: { scenario: ScenarioDetail }) {
  const [draft, setDraft] = useState<BasicsDraft>(() => basicsDraft(scenario));
  const saving = useScenarioSave(scenario.id);
  const hints = basicsHints(draft);
  const fields = saving.problem?.fields ?? {};

  function update(changes: Partial<BasicsDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit() {
    const saved = await saving.save(toBasicsBody(draft));
    // 서버가 다듬은 값(앞뒤 공백을 뗀 제목)으로 다시 채운다
    if (saved) setDraft(basicsDraft(saved));
  }

  return (
    <ScenarioForm
      label="기본"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
      actions={<DeleteAssetButton kind="scenarios" assetId={scenario.id} title={scenario.title} />}
    >
      <ModelStatusNotice scenario={scenario} />
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
        hint="내 시나리오 목록에서 알아보기 위한 짧은 설명입니다. 공개할 때의 한줄소개와 소개글은 소개 탭에서 씁니다."
      />
      <SelectField
        label="등급"
        name="rating"
        value={draft.rating}
        onChange={(event) => update({ rating: event.target.value as Rating })}
        error={fields.rating}
        hint="성인용은 본인인증으로 성인 확인을 한 사람만 고를 수 있고, 성인 확인을 한 사람에게만 보입니다."
      >
        {Object.entries(RATINGS).map(([rating, label]) => (
          <option key={rating} value={rating}>
            {label}
          </option>
        ))}
      </SelectField>
      <ModelSelect
        value={draft.narrationModel}
        onChange={(narrationModel) => update({ narrationModel })}
        error={hints.narration_model ?? fields.narration_model}
      />
      <SelectField
        label="추천 서술 문체"
        name="narration_style"
        value={draft.narrationStyle}
        onChange={(event) => update({ narrationStyle: event.target.value as NarrationStyle })}
        hint="테이블을 여는 사람이 바꿀 수 있습니다."
      >
        {NARRATION_STYLE_VALUES.map((style) => (
          <option key={style} value={style}>
            {narrationStyleLabel(style)}
          </option>
        ))}
      </SelectField>
      <ClockFields draft={draft} hints={hints} update={update} />
    </ScenarioForm>
  );
}

function ModelStatusNotice({ scenario }: { scenario: ScenarioDetail }) {
  const models = useQuery(narrationModelsQuery());
  const nameOf = (slug: string) => models.data?.models.find((model) => model.slug === slug)?.display_name ?? slug;
  const text = modelStatusText(scenario.narration_model_status, nameOf);
  return text ? <Notice tone="error">{text}</Notice> : null;
}

type ClockProps = {
  draft: BasicsDraft;
  hints: Record<string, string>;
  update: (changes: Partial<BasicsDraft>) => void;
};

function ClockFields({ draft, hints, update }: ClockProps) {
  return (
    <fieldset className="scenario-clock">
      <legend>게임 안의 시계</legend>
      <p className="ui-field__hint">테이블이 시작하는 날과 시각, 라운드 하나에 흐르는 시간입니다. 라운드의 시간은 방장이 라운드마다 바꿀 수 있습니다.</p>
      <TextField
        label="시작하는 날(며칠째)"
        name="start_day"
        inputMode="numeric"
        value={draft.startDay}
        onChange={(event) => update({ startDay: event.target.value })}
        error={hints.start_day}
      />
      <TextField
        label="시작하는 시각(시, 0~23)"
        name="start_hour"
        inputMode="numeric"
        value={draft.startHour}
        onChange={(event) => update({ startHour: event.target.value })}
        error={hints.start_hour}
      />
      <TextField
        label="라운드 하나에 흐르는 시간(분)"
        name="round_minutes"
        inputMode="numeric"
        value={draft.roundMinutes}
        onChange={(event) => update({ roundMinutes: event.target.value })}
        error={hints.round_minutes}
      />
    </fieldset>
  );
}
