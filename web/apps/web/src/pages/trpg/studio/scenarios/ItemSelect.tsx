// web/apps/web/src/pages/trpg/studio/scenarios/ItemSelect.tsx
// 물건 항목 하나 고르기(B9). 길의 문(열쇠, 따는 도구, 고치는 도구)과 자물쇠 물건(새 열쇠, 따는 도구)이 함께 쓴다.
// 고른 것이 붙인 로어북에 없으면 "(붙인 로어북에 없는 물건)"으로 남겨 보인다.

import { SelectField } from '@ai-trpg/ui';
import type { EntryChoice } from './useLoreEntries';

type Props = {
  label: string;
  value: string;
  items: EntryChoice[];
  /** 빈 값의 글("고르기", "도구 없이") */
  empty: string;
  onChange: (id: string) => void;
  error?: string | undefined;
};

export function ItemSelect({ label, value, items, empty, onChange, error }: Props) {
  return (
    <SelectField label={label} value={value} onChange={(event) => onChange(event.target.value)} error={error}>
      <option value="">{empty}</option>
      {value !== '' && !items.some((item) => item.id === value) ? <option value={value}>(붙인 로어북에 없는 물건)</option> : null}
      {items.map((item) => (
        <option key={item.id} value={item.id}>
          {item.name}
        </option>
      ))}
    </SelectField>
  );
}
