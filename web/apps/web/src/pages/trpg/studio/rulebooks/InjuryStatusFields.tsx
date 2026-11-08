// web/apps/web/src/pages/trpg/studio/rulebooks/InjuryStatusFields.tsx
// 룰북의 짧은 부상(상태 이상)마다 라운드마다의 피해와 벗어나기(#254)를 고른다. 독, 출혈, 거미줄 같은 것이다.
// 부상 자체(이름, 효과, 라운드 수)는 템플릿의 것이라 여기서 고치지 않는다. 고르는 값은 injuryStatusForm.ts 가 다룬다.

import { SelectField } from '@ai-trpg/ui';
import { magnitudeLabel, withRow, type StatusDraft, type StatusRow, type StatusRules } from './injuryStatusForm';

type Props = {
  statuses: StatusDraft;
  onChange: (statuses: StatusDraft) => void;
};

export function InjuryStatusFields({ statuses, onChange }: Props) {
  if (statuses.rows.length === 0) return null;
  return (
    <fieldset className="scenario-choices">
      <legend>상태 이상</legend>
      <p className="ui-field__hint">
        짧은 부상마다 라운드가 닫힐 때 입히는 피해와, 판정으로 벗어나는 법을 고릅니다. 걸린 라운드에는 들지 않고 다음 라운드부터 듭니다.
      </p>
      {statuses.rows.map((row) => (
        <StatusRowFields
          key={row.key}
          row={row}
          rules={statuses.rules}
          onChange={(changes) => onChange(withRow(statuses, row.key, changes))}
        />
      ))}
    </fieldset>
  );
}

type RowProps = {
  row: StatusRow;
  rules: StatusRules;
  onChange: (changes: Partial<StatusRow>) => void;
};

/** 짧은 부상 하나의 피해와 벗어나기 */
function StatusRowFields({ row, rules, onChange }: RowProps) {
  return (
    <fieldset className="scenario-choices" aria-label={`상태 ${row.name}`}>
      <legend>{row.name}</legend>
      <SelectField label="라운드마다의 피해" value={row.magnitude} onChange={(event) => onChange({ magnitude: event.target.value })}>
        <option value="">피해 없음</option>
        {rules.magnitudes.map((magnitude) => (
          <option key={magnitude.key} value={magnitude.key}>
            {magnitudeLabel(magnitude)}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="피해의 성질"
        value={row.nature}
        disabled={row.magnitude === ''}
        onChange={(event) => onChange({ nature: event.target.value })}
        hint="성질이 있으면 입은 쪽의 저항과 면역을 따릅니다."
      >
        <option value="">성질 없음</option>
        {rules.natures.map((nature) => (
          <option key={nature.key} value={nature.key}>
            {nature.name}
          </option>
        ))}
      </SelectField>
      <SelectField label="벗어나는 판정의 능력치" value={row.ability} onChange={(event) => onChange({ ability: event.target.value })}>
        <option value="">벗어날 수 없음(라운드가 지나야 풀림)</option>
        {rules.abilities.map((ability) => (
          <option key={ability.key} value={ability.key}>
            {ability.name}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="벗어나는 판정의 난이도"
        value={row.difficulty}
        disabled={row.ability === ''}
        onChange={(event) => onChange({ difficulty: event.target.value })}
      >
        <option value="">기본 난이도</option>
        {rules.difficulties.map((difficulty) => (
          <option key={difficulty.key} value={difficulty.key}>
            {difficulty.name}
          </option>
        ))}
      </SelectField>
    </fieldset>
  );
}
