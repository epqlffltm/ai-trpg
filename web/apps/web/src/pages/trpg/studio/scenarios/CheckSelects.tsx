// web/apps/web/src/pages/trpg/studio/scenarios/CheckSelects.tsx
// 판정 하나의 고르기(B9 지도): 능력치와 난이도, 고르면 실패의 피해(양의 등급). 숨긴 길·숨긴 물건의 찾기, 넘기, 따기, 부수기, 고치기가 함께 쓴다.
// 이름표는 룰북에서 고른다. 난이도를 비우면 룰북의 기본이다. 룰북이 없으면 고를 수 없다고 적는다.

import { SelectField } from '@ai-trpg/ui';
import type { Ruleset } from '../../../../api/types';

type Props = {
  /** 판정의 이름. "찾는 판정" */
  label: string;
  rules: Ruleset | null;
  ability: string;
  difficulty: string;
  onChange: (changes: { ability?: string; difficulty?: string; harm?: string }) => void;
  error?: string | undefined;
  /** 실패의 피해를 고르게 하려면 그 값(넘기 판정) */
  harm?: string;
};

export function CheckSelects({ label, rules, ability, difficulty, onChange, error, harm }: Props) {
  if (!rules) return <p className="ui-field__error">{label}은 룰북의 능력치로 정합니다. 룰북을 먼저 고르세요.</p>;
  return (
    <div className="scenario-players__row">
      <SelectField label={`${label}의 능력치`} value={ability} onChange={(event) => onChange({ ability: event.target.value })} error={error}>
        <option value="">고르기</option>
        {rules.abilities.map((one) => (
          <option key={one.key} value={one.key}>
            {one.name}
          </option>
        ))}
      </SelectField>
      <SelectField label={`${label}의 난이도`} value={difficulty} onChange={(event) => onChange({ difficulty: event.target.value })}>
        <option value="">룰북의 기본</option>
        {rules.difficulties.map((one) => (
          <option key={one.key} value={one.key}>
            {one.name}
          </option>
        ))}
      </SelectField>
      {harm !== undefined ? (
        <SelectField label={`${label}에 실패하면 다치는 양`} value={harm} onChange={(event) => onChange({ harm: event.target.value })}>
          <option value="">다치지 않음</option>
          {rules.magnitudes.map((one) => (
            <option key={one.key} value={one.key}>
              {one.name}({one.count}d{one.sides})
            </option>
          ))}
        </SelectField>
      ) : null}
    </div>
  );
}
