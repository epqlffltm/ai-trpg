// web/apps/web/src/pages/trpg/tables/ModelSelect.tsx
// 서술 모델 고르기. 고를 수 있는 것과 1인 1라운드의 값은 GET /tables/narration-models(B8)다. 묶음(기본, 표준, 프리미엄) 차례로 보인다.
// 비우면(처음 값) 시나리오의 추천 모델이고, 쓸 수 없으면 서버가 같은 회사의 대체 모델로 정한다.
// 결제 서버 없이 도는 서버(free)면 값이 없다. 목록을 읽지 못해도 추천으로 만들 수 있게 칸은 남긴다.

import { SelectField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import type { NarrationModel } from '../../../api/types';
import { narrationModelsQuery } from '../queries';

const GRADE_ORDER: Record<NarrationModel['grade'], number> = { basic: 0, standard: 1, premium: 2 };
const GRADE_LABELS: Record<NarrationModel['grade'], string> = { basic: '기본', standard: '표준', premium: '프리미엄' };

type Props = {
  value: string;
  recommended: string | null;
  onChange: (slug: string) => void;
  error?: string | undefined;
};

export function ModelSelect({ value, recommended, onChange, error }: Props) {
  const models = useQuery(narrationModelsQuery());
  const offered = sortByGrade(models.data?.models ?? []);
  const recommendedName = offered.find((model) => model.slug === recommended)?.display_name;
  return (
    <SelectField
      label="서술 모델"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      error={error}
      hint={models.isError ? '모델 목록을 불러오지 못했습니다. 시나리오의 추천으로 만들 수 있습니다.' : '값은 라운드마다 한 사람에게 매겨집니다.'}
    >
      <option value="">{recommendedName ? `시나리오의 추천(${recommendedName})` : '시나리오의 추천'}</option>
      {offered.map((model) => (
        <option key={model.slug} value={model.slug}>
          {modelOptionLabel(model)}
        </option>
      ))}
    </SelectField>
  );
}

/** "표준 · Gemini Flash · 40 크레딧". 값이 없으면(free) 값을 빼고, 골드로만 낼 수 있으면 그렇게 적는다 */
export function modelOptionLabel(model: NarrationModel): string {
  const parts = [GRADE_LABELS[model.grade], model.display_name];
  if (model.credits !== null) parts.push(`${model.credits} 크레딧${model.tier === 'premium' ? '(골드만)' : ''}`);
  return parts.join(' · ');
}

function sortByGrade(models: NarrationModel[]): NarrationModel[] {
  return [...models].sort((a, b) => GRADE_ORDER[a.grade] - GRADE_ORDER[b.grade]);
}
