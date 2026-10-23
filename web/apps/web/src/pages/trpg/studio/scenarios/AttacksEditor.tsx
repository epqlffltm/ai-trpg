// web/apps/web/src/pages/trpg/studio/scenarios/AttacksEditor.tsx
// 시트의 공격들을 고치는 칸(B9). 인물 시트(와 몬스터 시트)가 쓴다. 공격마다 이름, 능력치, 난이도, 피해의 양, 무기.
// 이름표는 룰북에서 고르고, 무기는 지금 장비 줄의 물건에서 고른다(공격 보정이 없는 물건은 그렇다고 적는다). 검사는 attacksForm.ts.

import { Button, SelectField, TextField } from '@ai-trpg/ui';
import type { ItemRule, Ruleset } from '../../../../api/types';
import { ATTACK_NAME_MAX, MAX_ATTACKS, newAttack, type AttackDraft } from './attacksForm';
import { entryName, type EntryChoice } from './useLoreEntries';

type Props = {
  drafts: AttackDraft[];
  onChange: (drafts: AttackDraft[]) => void;
  rules: Ruleset;
  /** 장비 줄의 물건들 */
  equipment: string[];
  entries: EntryChoice[];
  itemRules: ItemRule[];
  hints: Record<number, string>;
};

export function AttacksEditor({ drafts, onChange, rules, equipment, entries, itemRules, hints }: Props) {
  const first = { ability: rules.abilities[0]?.key ?? '', difficulty: rules.default_difficulty, harm: rules.magnitudes[0]?.key ?? '' };
  const change = (index: number, draft: AttackDraft) => onChange(drafts.map((one, at) => (at === index ? draft : one)));
  return (
    <div className="scenario-stacks">
      {drafts.length === 0 ? <p className="hint">공격이 없으면 싸움이 붙어도 치지 않습니다.</p> : null}
      {drafts.map((draft, index) => (
        <fieldset key={index} className="scenario-stack">
          <legend>공격 {index + 1}</legend>
          <div className="scenario-players__row">
            <TextField label="이름" maxLength={ATTACK_NAME_MAX} value={draft.name} onChange={(event) => change(index, { ...draft, name: event.target.value })} />
            <SelectField label="능력치" value={draft.ability} onChange={(event) => change(index, { ...draft, ability: event.target.value })}>
              <KeyOptions value={draft.ability} choices={rules.abilities} />
            </SelectField>
            <SelectField label="난이도" value={draft.difficulty} onChange={(event) => change(index, { ...draft, difficulty: event.target.value })}>
              <KeyOptions value={draft.difficulty} choices={rules.difficulties} />
            </SelectField>
            <SelectField label="피해의 양" value={draft.harm} onChange={(event) => change(index, { ...draft, harm: event.target.value })}>
              <KeyOptions value={draft.harm} choices={rules.magnitudes} />
            </SelectField>
            <SelectField label="무기" value={draft.weapon} onChange={(event) => change(index, { ...draft, weapon: event.target.value })}>
              <option value="">맨몸</option>
              {draft.weapon !== '' && !equipment.includes(draft.weapon) ? <option value={draft.weapon}>(장비에 없는 물건)</option> : null}
              {equipment.map((entryId) => (
                <option key={entryId} value={entryId}>
                  {entryName(entries, entryId)}
                  {itemRules.find((rule) => rule.entry_id === entryId)?.attack ? '' : '(공격 보정 없음)'}
                </option>
              ))}
            </SelectField>
          </div>
          {hints[index] ? <p className="ui-field__error">{hints[index]}</p> : null}
          <Button variant="quiet" aria-label={`공격 ${index + 1} 지우기`} onClick={() => onChange(drafts.filter((_, at) => at !== index))}>
            지우기
          </Button>
        </fieldset>
      ))}
      <p>
        <Button variant="secondary" disabled={drafts.length >= MAX_ATTACKS} onClick={() => onChange([...drafts, newAttack(first)])}>
          공격 더하기
        </Button>{' '}
        <span className="hint">
          {drafts.length} / {MAX_ATTACKS}
        </span>
      </p>
    </div>
  );
}

/** 룰북의 이름표 고르기. 지금 값이 룰북에 없으면(룰북을 바꿨다) 그 값을 남겨 둔다 */
function KeyOptions({ value, choices }: { value: string; choices: readonly { key: string; name: string }[] }) {
  return (
    <>
      {value === '' ? <option value="">고르기</option> : null}
      {value !== '' && !choices.some((choice) => choice.key === value) ? <option value={value}>{value}(룰북에 없음)</option> : null}
      {choices.map((choice) => (
        <option key={choice.key} value={choice.key}>
          {choice.name}
        </option>
      ))}
    </>
  );
}
