// web/apps/web/src/pages/trpg/studio/rulebooks/DefenseFields.tsx
// 막는 능력치(#254, 맞서는 굴림) 고르기. 몬스터와 NPC 의 공격을 받는 쪽이 이 능력치로 굴리고, 공격하는 쪽의 합이 더 높아야 맞는다.
// 공격마다 따로 정할 수 있다(시트의 공격 칸). 비울 수 없다. 지금 값이 능력치에 없으면(옛 룰북) 그 값을 남겨 보인다.

import { SelectField } from '@ai-trpg/ui';
import type { Ability } from '../../../../api/types';

type Props = {
  defense: string;
  abilities: Ability[];
  hint: string | undefined;
  onChange: (defense: string) => void;
};

export function DefenseFields({ defense, abilities, hint, onChange }: Props) {
  return (
    <fieldset className="choice-list">
      <legend>막는 규칙</legend>
      <SelectField
        label="막는 능력치"
        name="defense"
        value={defense}
        onChange={(event) => onChange(event.target.value)}
        error={hint}
        hint="몬스터와 NPC 의 공격을 받는 쪽이 이 능력치로 맞서 굴립니다. 공격하는 쪽의 합이 더 높아야 맞고, 같으면 막습니다. 공격마다 시트에서 따로 정할 수 있습니다."
      >
        {defense === '' ? <option value="">고르기</option> : null}
        {defense !== '' && !abilities.some((ability) => ability.key === defense) ? <option value={defense}>{defense}(능력치에 없음)</option> : null}
        {abilities.map((ability) => (
          <option key={ability.key} value={ability.key}>
            {ability.name}
          </option>
        ))}
      </SelectField>
    </fieldset>
  );
}
