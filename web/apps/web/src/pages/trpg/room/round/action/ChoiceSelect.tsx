// web/apps/web/src/pages/trpg/room/round/action/ChoiceSelect.tsx
// 고를 거리(Choice) 목록으로 만든 고르기 칸. 빈 값을 둘 때는 그 글(empty)을 맨 앞에 둔다.

import { SelectField } from '@ai-trpg/ui';
import type { Choice } from './actionOptions';

type Props = {
  label: string;
  value: string;
  choices: Choice[];
  onChange: (value: string) => void;
  /** 빈 값의 글. 없으면 빈 값을 두지 않는다 */
  empty?: string;
  hint?: string;
};

export function ChoiceSelect({ label, value, choices, onChange, empty, hint }: Props) {
  return (
    <SelectField label={label} value={value} onChange={(event) => onChange(event.target.value)} hint={hint}>
      {empty !== undefined ? <option value="">{empty}</option> : null}
      {choices.map((choice) => (
        <option key={choice.value} value={choice.value}>
          {choice.label}
        </option>
      ))}
    </SelectField>
  );
}
