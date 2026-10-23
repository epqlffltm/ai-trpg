// web/apps/web/src/pages/trpg/studio/scenarios/ItemRulesSection.tsx
// 물건 규칙(B9 물건·돈 탭). 붙인 로어북의 물건 항목을 모두 늘어놓고, 줄마다 규칙(없으면 "장비 · 보통")을 보인다.
// 줄을 고치면 창이 열리고, 창의 저장이 물건 규칙의 목록을 통째로 바로 보낸다. 규칙 지우기는 장비·보통으로 돌린다.
// 붙인 로어북에 없는 물건의 규칙(로어북을 뗐거나 항목을 지웠다)도 줄로 남겨 지울 수 있게 한다.

import { Button, Checkbox, Dialog, SelectField, TextField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent } from 'react';
import type { ItemKind, ItemRarity, ItemRule, Ruleset, ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { ITEM_KIND_VALUES, itemKindLabel, RARITY_VALUES, rarityLabel } from '../../labels';
import {
  COMBAT_FIELDS,
  COMBAT_LABELS,
  isWorn,
  itemRuleDraft,
  itemRuleHints,
  itemRuleLine,
  toggleSlot,
  toItemRule,
  withItemRule,
  withoutItemRule,
  type ItemRuleDraft,
} from './itemRuleForm';
import type { ItemEntry } from './useItemEntries';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail; rules: Ruleset | null; entries: ItemEntry[] };

type Row = { id: string; name: string; listed: boolean };

/** 물건 항목의 줄들과, 항목이 없는 규칙의 줄들 */
function rowsOf(entries: ItemEntry[], itemRules: ItemRule[]): Row[] {
  const listed = entries.map((entry) => ({ id: entry.id, name: entry.name, listed: true }));
  const orphans = itemRules
    .filter((rule) => !entries.some((entry) => entry.id === rule.entry_id))
    .map((rule) => ({ id: rule.entry_id, name: '(붙인 로어북에 없는 물건)', listed: false }));
  return [...listed, ...orphans];
}

export function ItemRulesSection({ scenario, rules, entries }: Props) {
  const [editing, setEditing] = useState<Row | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const rows = rowsOf(entries, scenario.items);
  return (
    <section className="page-section" aria-labelledby="item-rules-heading">
      <h2 id="item-rules-heading">물건 규칙</h2>
      <p className="hint">붙인 로어북의 물건 항목마다 엔진에서 무엇인지 정합니다. 규칙이 없으면 착용하지 않는 장비이고 등급은 보통입니다. 창에서 저장하면 바로 저장됩니다.</p>
      {rows.length === 0 ? <p className="hint">붙인 로어북에 물건 항목이 없습니다. 로어북에 종류가 물건인 항목을 더하세요.</p> : null}
      <ul className="plain-list studio-list" aria-label="물건 규칙">
        {rows.map((row) => {
          const rule = scenario.items.find((one) => one.entry_id === row.id);
          return (
            <li key={row.id} className="studio-list__item studio-item">
              <div>
                <strong>{row.name}</strong>
                <div className="studio-list__description hint">{itemRuleLine(rule, rules) ?? '규칙 없음(장비 · 보통)'}</div>
              </div>
              <Button variant="quiet" aria-label={`${row.name} 규칙 고치기`} onClick={() => setEditing(row)}>
                고치기
              </Button>
            </li>
          );
        })}
      </ul>
      <Dialog title={editing ? `물건 규칙: ${editing.name}` : '물건 규칙'} open={editing !== null} onClose={close}>
        {editing ? <ItemRuleForm scenario={scenario} rules={rules} row={editing} done={close} /> : null}
      </Dialog>
    </section>
  );
}

type FormProps = { scenario: ScenarioDetail; rules: Ruleset | null; row: Row; done: () => void };

function ItemRuleForm({ scenario, rules, row, done }: FormProps) {
  const rule = scenario.items.find((one) => one.entry_id === row.id);
  const [draft, setDraft] = useState<ItemRuleDraft>(() => itemRuleDraft(rule));
  const saving = useScenarioSave(scenario.id);
  const hints = itemRuleHints(draft);
  const blocked = Object.keys(hints).length > 0;

  function update(changes: Partial<ItemRuleDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    if (await saving.save({ items: withItemRule(scenario.items, toItemRule(row.id, draft)) })) done();
  }

  async function clear() {
    if (await saving.save({ items: withoutItemRule(scenario.items, row.id) })) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="물건 규칙">
      <ProblemNotice problem={saving.problem} />
      {row.listed ? (
        <>
          <div className="scenario-players__row">
            <SelectField label="종류" value={draft.kind} onChange={(event) => update({ kind: event.target.value as ItemKind })}>
              {ITEM_KIND_VALUES.map((kind) => (
                <option key={kind} value={kind}>
                  {itemKindLabel(kind)}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="등급"
              value={draft.rarity}
              onChange={(event) => update({ rarity: event.target.value as ItemRarity })}
              hint="높을수록 훔치기 어렵습니다."
            >
              {RARITY_VALUES.map((rarity) => (
                <option key={rarity} value={rarity}>
                  {rarityLabel(rarity)}
                </option>
              ))}
            </SelectField>
          </div>
          <TextField
            label="값(선택)"
            inputMode="numeric"
            value={draft.price}
            onChange={(event) => update({ price: event.target.value })}
            error={hints.price}
          />
          <p className="ui-field__hint">
            상인이 파는 값입니다. 비우면 사고팔 수 없습니다.{scenario.currency ? '' : ' 화폐가 없으면 게시 점검이 알립니다.'}
          </p>
          {draft.kind === 'consumable' ? <HealsField draft={draft} rules={rules} update={update} /> : <WearFields draft={draft} rules={rules} hints={hints} update={update} />}
        </>
      ) : (
        <p>이 물건은 붙인 로어북에 없어 테이블에서 쓰이지 않습니다. 규칙을 지우거나, 그 물건이 있는 로어북을 다시 붙이세요.</p>
      )}
      <div className="actions">
        {row.listed ? (
          <Button type="submit" busy={saving.busy} disabled={blocked}>
            저장
          </Button>
        ) : null}
        {rule ? (
          <Button variant="quiet" disabled={saving.busy} onClick={() => void clear()}>
            규칙 지우기
          </Button>
        ) : null}
      </div>
    </form>
  );
}

type FieldsProps = { draft: ItemRuleDraft; rules: Ruleset | null; update: (changes: Partial<ItemRuleDraft>) => void };

function HealsField({ draft, rules, update }: FieldsProps) {
  const magnitudes = rules?.magnitudes ?? [];
  return (
    <SelectField
      label="쓰면 회복하는 양"
      value={draft.heals}
      onChange={(event) => update({ heals: event.target.value })}
      hint={rules ? '룰북의 양의 등급입니다. 비우면 써도 HP 가 바뀌지 않습니다.' : '룰북을 고르면 양의 등급을 고를 수 있습니다.'}
    >
      <option value="">회복하지 않음</option>
      {draft.heals !== '' && !magnitudes.some((entry) => entry.key === draft.heals) ? <option value={draft.heals}>{draft.heals}(룰북에 없음)</option> : null}
      {magnitudes.map((entry) => (
        <option key={entry.key} value={entry.key}>
          {entry.name}({entry.count}d{entry.sides})
        </option>
      ))}
    </SelectField>
  );
}

function WearFields({ draft, rules, hints, update }: FieldsProps & { hints: Record<string, string> }) {
  const slots = rules?.equipment_slots ?? [];
  const order = slots.map((slot) => slot.key);
  if (slots.length === 0) return <p className="hint">{rules ? '이 룰북에는 장비의 칸이 없어 착용하지 않습니다.' : '룰북을 고르면 착용할 칸을 고를 수 있습니다.'}</p>;
  return (
    <>
      <fieldset className="scenario-choices">
        <legend>착용할 수 있는 칸</legend>
        <p className="ui-field__hint">비우면 착용하지 않는 물건입니다. 두 손 검은 주손과 보조손을 고르고 2칸을 차지하게 합니다.</p>
        {slots.map((slot) => (
          <Checkbox
            key={slot.key}
            label={slot.name}
            checked={draft.slots.includes(slot.key)}
            onChange={() => update({ slots: toggleSlot(draft.slots, slot.key, order) })}
          />
        ))}
      </fieldset>
      {isWorn(draft) ? (
        <>
          <TextField
            label="차지하는 칸의 수"
            inputMode="numeric"
            value={draft.slotCount}
            onChange={(event) => update({ slotCount: event.target.value })}
            error={hints.slot_count}
          />
          <fieldset className="scenario-choices">
            <legend>공격과 방어(선택, 1~10)</legend>
            <div className="ability-grid">
              {COMBAT_FIELDS.map((field) => (
                <TextField
                  key={field}
                  label={COMBAT_LABELS[field]}
                  inputMode="numeric"
                  value={draft.combat[field]}
                  onChange={(event) => update({ combat: { ...draft.combat, [field]: event.target.value } })}
                  error={hints[field]}
                />
              ))}
            </div>
          </fieldset>
        </>
      ) : null}
    </>
  );
}
