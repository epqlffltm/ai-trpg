// web/apps/web/src/pages/trpg/studio/scenarios/ModelSelect.tsx
// 시나리오의 추천 서술 모델 고르기(B9). 테이블을 열 때 방장이 바꿀 수 있고, 고르지 않으면 이 모델이다.
// 단계(기억과 장면의 양)는 테이블에서 고르므로 여기서는 모델만 고른다. 목록은 회사별로 묶는다(ModelPicker 와 같다).
// 지금 목록에 없는 모델(서비스를 마친 것)을 가리키고 있으면 그 이름을 남겨 두고 고를 수 없다고 적는다.

import { SelectField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { groupByVendor, modelOptionLabel } from '../../models/modelChoice';
import { narrationModelsQuery } from '../../queries';

type Props = { value: string; onChange: (slug: string) => void; error?: string | undefined };

export function ModelSelect({ value, onChange, error }: Props) {
  const models = useQuery(narrationModelsQuery());
  const list = models.data?.models ?? [];
  const missing = value !== '' && !list.some((model) => model.slug === value);
  return (
    <SelectField
      label="추천 서술 모델"
      name="narration_model"
      value={value}
      error={error}
      hint={models.isError ? '모델 목록을 불러오지 못했습니다.' : '테이블을 여는 사람이 바꿀 수 있습니다. 바꾸지 않으면 이 모델로 서술합니다.'}
      onChange={(event) => onChange(event.target.value)}
    >
      {value === '' ? <option value="">고르기</option> : null}
      {missing ? <option value={value}>{models.isSuccess ? `${value}(지금 고를 수 없음)` : value}</option> : null}
      {groupByVendor(list).map((group) => (
        <optgroup key={group.vendor} label={group.vendor}>
          {group.models.map((model) => (
            <option key={model.slug} value={model.slug}>
              {modelOptionLabel(model)}
            </option>
          ))}
        </optgroup>
      ))}
    </SelectField>
  );
}
