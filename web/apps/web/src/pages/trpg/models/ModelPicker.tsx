// web/apps/web/src/pages/trpg/models/ModelPicker.tsx
// 서술 모델과 단계 고르기(B8). 테이블 만들기(B4)와 방장의 운영(B6 ⑤)이 함께 쓴다.
// 모델은 회사별로 묶어 보인다. 고른 모델이 단계를 여럿 팔면 기억(입력)과 장면(출력)의 단계를 고른다.
// 아래에 고른 것의 값(1인 1라운드), 예약된 바뀜, 종료일을 보인다. 값이 없으면(free) 이름만 보인다.
// 목록을 읽지 못해도 추천으로 만들 수 있게(B4) 칸은 남긴다.

import { SelectField } from '@ai-trpg/ui';
import type { NarrationModels } from '../../../api/types';
import {
  chosenModel,
  findOption,
  groupByVendor,
  inputSteps,
  modelOptionLabel,
  nextText,
  outputSteps,
  priceText,
  retireText,
  stepLabel,
  withInputStep,
  withModel,
  type ModelValue,
} from './modelChoice';

type Props = {
  models: NarrationModels | undefined;
  failed: boolean;
  value: ModelValue;
  onChange: (value: ModelValue) => void;
  /** 시나리오의 추천 모델. 주면 "시나리오의 추천"(빈 값)을 고를 거리에 둔다 */
  recommended?: string | null | undefined;
  error?: string | undefined;
  disabled?: boolean;
};

export function ModelPicker({ models, failed, value, onChange, recommended, error, disabled }: Props) {
  const list = models?.models ?? [];
  const allowRecommended = recommended !== undefined;
  const model = chosenModel(list, value, recommended ?? null);
  const recommendedName = list.find((entry) => entry.slug === recommended)?.display_name;
  const inputs = inputSteps(model);
  const outputs = outputSteps(model, value.inputStep);
  return (
    <div className="model-picker">
      <SelectField
        label="서술 모델"
        value={value.model}
        disabled={disabled}
        error={error}
        hint={failed ? '모델 목록을 불러오지 못했습니다.' : undefined}
        onChange={(event) => onChange(withModel(list, value, event.target.value, recommended ?? null))}
      >
        {allowRecommended ? (
          <option value="">{recommendedName ? `시나리오의 추천(${recommendedName})` : '시나리오의 추천'}</option>
        ) : null}
        {!allowRecommended && !list.some((entry) => entry.slug === value.model) ? (
          <option value={value.model}>{value.model || '고르기'}(지금 고를 수 없음)</option>
        ) : null}
        {groupByVendor(list).map((group) => (
          <optgroup key={group.vendor} label={group.vendor}>
            {group.models.map((entry) => (
              <option key={entry.slug} value={entry.slug}>
                {modelOptionLabel(entry)}
              </option>
            ))}
          </optgroup>
        ))}
      </SelectField>
      {inputs.length > 1 || outputs.length > 1 ? (
        <div className="ability-grid">
          <SelectField
            label="기억(서술에 넣는 지난 이야기)"
            value={String(value.inputStep)}
            disabled={disabled}
            onChange={(event) => onChange(withInputStep(model, value, Number(event.target.value)))}
          >
            {inputs.map((entry) => (
              <option key={entry.step} value={entry.step}>
                {stepLabel(entry.step, entry.tokens)}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="장면의 길이"
            value={String(value.outputStep)}
            disabled={disabled}
            onChange={(event) => onChange({ ...value, outputStep: Number(event.target.value) })}
          >
            {outputs.map((entry) => (
              <option key={entry.step} value={entry.step}>
                {stepLabel(entry.step, entry.tokens)}
              </option>
            ))}
          </SelectField>
        </div>
      ) : null}
      <ModelPrice models={models} value={value} recommended={recommended ?? null} />
    </div>
  );
}

/** 고른 모델과 단계의 값, 예약된 바뀜, 종료일 */
export function ModelPrice({ models, value, recommended }: { models: NarrationModels | undefined; value: ModelValue; recommended: string | null }) {
  const model = chosenModel(models?.models ?? [], value, recommended);
  const option = findOption(model, value.inputStep, value.outputStep);
  const lines = [priceText(option), nextText(option?.next), retireText(model?.retires_on ?? null)].filter(Boolean);
  if (models?.free) lines.unshift('결제 서버 없이 도는 서버라 값을 받지 않습니다.');
  if (lines.length === 0) return null;
  return <p className="hint model-price">{lines.join(' · ')}</p>;
}
