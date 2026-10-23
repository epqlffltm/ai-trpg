// web/apps/web/src/pages/trpg/studio/scenarios/StacksEditor.tsx
// 소지품의 줄들을 고치는 칸(B9). 시작 소지품과 프리젠의 소지품이 함께 쓴다.
// 줄마다 물건(붙인 로어북의 물건 항목), 개수, 그 물건의 규칙에 칸이 있으면 시작할 때 착용할 칸. 검사는 stacksForm.ts.

import { Button, Checkbox, SelectField, TextField } from '@ai-trpg/ui';
import type { ItemRule, Ruleset } from '../../../../api/types';
import { changeStack, newStack, removeStack, STACK_MAX, wearableSlots, withEntry, type StackDraft } from './stacksForm';
import { toggleSlot } from './itemRuleForm';
import type { ItemEntry } from './useItemEntries';

type Props = {
  /** 줄의 이름. "시작 소지품" */
  label: string;
  drafts: StackDraft[];
  onChange: (drafts: StackDraft[]) => void;
  entries: ItemEntry[];
  itemRules: ItemRule[];
  rules: Ruleset | null;
  hints: Record<number, string>;
  max: number;
};

export function StacksEditor({ label, drafts, onChange, entries, itemRules, rules, hints, max }: Props) {
  const ids = entries.map((entry) => entry.id);
  return (
    <div className="scenario-stacks">
      {drafts.length === 0 ? <p className="hint">아직 없습니다.</p> : null}
      {drafts.map((draft, index) => (
        <StackRow
          key={index}
          legend={`${label} ${index + 1}`}
          draft={draft}
          entries={entries}
          itemRules={itemRules}
          rules={rules}
          hint={hints[index]}
          onChange={(next) => onChange(changeStack(drafts, index, next))}
          onRemove={() => onChange(removeStack(drafts, index))}
        />
      ))}
      <p>
        <Button variant="secondary" disabled={drafts.length >= max || entries.length === 0} onClick={() => onChange([...drafts, newStack(drafts, ids)])}>
          {label} 더하기
        </Button>{' '}
        <span className="hint">
          {drafts.length} / {max}
        </span>
      </p>
    </div>
  );
}

type RowProps = {
  legend: string;
  draft: StackDraft;
  entries: ItemEntry[];
  itemRules: ItemRule[];
  rules: Ruleset | null;
  hint: string | undefined;
  onChange: (draft: StackDraft) => void;
  onRemove: () => void;
};

function StackRow({ legend, draft, entries, itemRules, rules, hint, onChange, onRemove }: RowProps) {
  const slots = wearableSlots(itemRules, draft.entryId);
  const slotName = (key: string) => rules?.equipment_slots.find((slot) => slot.key === key)?.name ?? key;
  const listed = entries.some((entry) => entry.id === draft.entryId);
  return (
    <fieldset className="scenario-stack">
      <legend>{legend}</legend>
      <div className="scenario-players__row">
        <SelectField label="물건" value={draft.entryId} onChange={(event) => onChange(withEntry(draft, event.target.value))}>
          {draft.entryId === '' ? <option value="">고르기</option> : null}
          {!listed && draft.entryId !== '' ? <option value={draft.entryId}>(붙인 로어북에 없는 물건)</option> : null}
          {entries.map((entry) => (
            <option key={entry.id} value={entry.id}>
              {entry.name}
            </option>
          ))}
        </SelectField>
        <TextField
          label={`개수(1~${STACK_MAX})`}
          inputMode="numeric"
          value={draft.count}
          onChange={(event) => onChange({ ...draft, count: event.target.value })}
        />
      </div>
      {slots.length > 0 ? (
        <div className="scenario-stack__wear" role="group" aria-label={`${legend}의 착용`}>
          <p className="ui-field__hint">시작할 때 착용할 칸(비우면 들고만 시작)</p>
          {slots.map((slot) => (
            <Checkbox
              key={slot}
              label={slotName(slot)}
              checked={draft.wear.includes(slot)}
              onChange={() => onChange({ ...draft, wear: toggleSlot(draft.wear, slot, slots) })}
            />
          ))}
        </div>
      ) : null}
      {hint ? <p className="ui-field__error">{hint}</p> : null}
      <Button variant="quiet" aria-label={`${legend} 지우기`} onClick={onRemove}>
        지우기
      </Button>
    </fieldset>
  );
}
