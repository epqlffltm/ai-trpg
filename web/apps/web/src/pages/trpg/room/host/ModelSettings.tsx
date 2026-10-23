// web/apps/web/src/pages/trpg/room/host/ModelSettings.tsx
// 방장의 서술 모델과 단계 바꾸기(B8). 지금 모델과 값을 보이고, "바꾸기"를 누르면 고르는 칸을 연다.
// 모집 중에는 언제든, 시작한 뒤에는 지금 모델이나 단계를 쓸 수 없을 때만(목록에 없거나 그 단계를 팔지 않는다) 바꿀 수 있다.
// 바꾼 값은 다음 라운드부터 쓴다. 아직 서술하지 않은 지금 라운드는 서버가 함께 바꾼다.

import { Button } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { changeNarrationModel } from '../../../../api/tableHost';
import type { TableDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { modelUsable, stepName, type ModelValue } from '../../models/modelChoice';
import { ModelPicker, ModelPrice } from '../../models/ModelPicker';
import { narrationModelsQuery } from '../../queries';
import { useHostAction } from './useHostAction';

export function ModelSettings({ table }: { table: TableDetail }) {
  const models = useQuery(narrationModelsQuery());
  const action = useHostAction(table.id);
  const current: ModelValue = { model: table.narration_model ?? '', inputStep: table.input_step, outputStep: table.output_step };
  const [draft, setDraft] = useState<ModelValue | null>(null);
  const usable = modelUsable(models.data?.models ?? [], table.narration_model, table.input_step, table.output_step);
  const changeable = table.status === 'recruiting' || (models.isSuccess && !usable);

  async function save(value: ModelValue) {
    const after = await action.run(() => changeNarrationModel(table.id, value.model, value.inputStep, value.outputStep));
    if (after) setDraft(null);
  }

  return (
    <div className="host-model">
      <p className="waiting-room__label">서술 모델</p>
      <p>
        {models.data?.models.find((model) => model.slug === table.narration_model)?.display_name ?? table.narration_model ?? '서버의 기본 모델'}
        <span className="hint"> · 기억 {stepName(table.input_step)} · 장면 {stepName(table.output_step)}</span>
      </p>
      <ModelPrice models={models.data} value={current} recommended={null} />
      {!usable && models.isSuccess ? <p className="ui-field__error">지금 모델이나 단계를 쓸 수 없습니다. 바꾸지 않으면 서술하지 못합니다.</p> : null}
      <ProblemNotice problem={action.problem} />
      {draft ? (
        <>
          <ModelPicker models={models.data} failed={models.isError} value={draft} onChange={setDraft} disabled={action.busy} />
          <div className="form-actions">
            <Button busy={action.busy} disabled={!draft.model} onClick={() => void save(draft)}>
              이 모델로 바꾸기
            </Button>
            <Button variant="quiet" onClick={() => setDraft(null)}>
              그대로 두기
            </Button>
          </div>
        </>
      ) : changeable ? (
        <Button variant="secondary" onClick={() => setDraft(current)}>
          모델 바꾸기
        </Button>
      ) : (
        <p className="hint">시작한 뒤에는 지금 모델을 쓸 수 없을 때만 바꿀 수 있습니다.</p>
      )}
    </div>
  );
}
