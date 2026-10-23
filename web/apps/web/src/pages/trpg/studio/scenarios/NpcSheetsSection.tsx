// web/apps/web/src/pages/trpg/studio/scenarios/NpcSheetsSection.tsx
// 인물 시트(B9 인물 탭). 붙인 로어북의 인물 항목을 모두 늘어놓고, 줄마다 시트(없으면 "기본 인물 시트")를 한 줄로 보인다.
// 줄을 고치면 창이 열리고, 창의 저장이 인물 시트 목록을 통째로 바로 보낸다. 시트 지우기는 기본 인물 시트로 돌린다.
// 붙인 로어북의 인물이 아닌 것의 시트(로어북을 뗐거나 항목을 지웠다)도 줄로 남겨 지울 수 있게 한다.

import { Button, Checkbox, Dialog, Notice, SelectField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent, type ReactNode } from 'react';
import type { NpcAttitude, NpcCaught, NpcSheet, Ruleset, ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { ATTITUDE_VALUES, attitudeLabel } from '../../labels';
import { AttacksEditor } from './AttacksEditor';
import { CAUGHT_LABELS, hasNpcHints, npcDraft, npcHints, npcLine, toNpcSheet, withNpcSheet, withoutNpcSheet, type NpcDraft } from './npcForm';
import { SheetFields } from './SheetFields';
import { MAX_CARRIED_EQUIPMENT, MAX_CARRIED_INVENTORY } from './stacksForm';
import { StacksEditor } from './StacksEditor';
import type { EntryChoice } from './useLoreEntries';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail; rules: Ruleset | null; people: EntryChoice[]; items: EntryChoice[] };

type Row = { id: string; name: string; listed: boolean };

function rowsOf(people: EntryChoice[], npcSheets: NpcSheet[]): Row[] {
  const listed = people.map((person) => ({ id: person.id, name: person.name, listed: true }));
  const orphans = npcSheets
    .filter((npc) => !people.some((person) => person.id === npc.entry_id))
    .map((npc) => ({ id: npc.entry_id, name: '(붙인 로어북의 인물이 아님)', listed: false }));
  return [...listed, ...orphans];
}

export function NpcSheetsSection({ scenario, rules, people, items }: Props) {
  const [editing, setEditing] = useState<Row | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const rows = rowsOf(people, scenario.npc_sheets);
  return (
    <section className="page-section" aria-labelledby="npc-sheets-heading">
      <h2 id="npc-sheets-heading">인물 시트</h2>
      <p className="hint">붙인 로어북의 인물마다 숫자와 태도, 지닌 물건, 공격을 정합니다. 시트가 없으면 위의 기본 인물 시트를 받습니다. 창에서 저장하면 바로 저장됩니다.</p>
      {rows.length === 0 ? <p className="hint">붙인 로어북에 인물 항목이 없습니다. 로어북에 종류가 인물인 항목을 더하세요.</p> : null}
      <ul className="plain-list studio-list" aria-label="인물 시트">
        {rows.map((row) => {
          const npc = scenario.npc_sheets.find((one) => one.entry_id === row.id);
          return (
            <li key={row.id} className="studio-list__item studio-item">
              <div>
                <strong>{row.name}</strong>
                <div className="studio-list__description hint">{npc ? npcLine(npc, rules) : '시트 없음(기본 인물 시트)'}</div>
              </div>
              <Button variant="quiet" aria-label={`${row.name} 시트 고치기`} onClick={() => setEditing(row)}>
                고치기
              </Button>
            </li>
          );
        })}
      </ul>
      <Dialog title={editing ? `인물 시트: ${editing.name}` : '인물 시트'} open={editing !== null} onClose={close}>
        {editing ? <NpcForm scenario={scenario} rules={rules} items={items} row={editing} done={close} /> : null}
      </Dialog>
    </section>
  );
}

type FormProps = { scenario: ScenarioDetail; rules: Ruleset | null; items: EntryChoice[]; row: Row; done: () => void };

function NpcForm({ scenario, rules, items, row, done }: FormProps) {
  const npc = scenario.npc_sheets.find((one) => one.entry_id === row.id);
  const saving = useScenarioSave(scenario.id);

  async function clear() {
    if (await saving.save({ npc_sheets: withoutNpcSheet(scenario.npc_sheets, row.id) })) done();
  }

  const clearButton = npc ? (
    <Button variant="quiet" disabled={saving.busy} onClick={() => void clear()}>
      시트 지우기
    </Button>
  ) : null;

  if (!row.listed || !rules) {
    return (
      <div>
        <ProblemNotice problem={saving.problem} />
        <p>
          {row.listed
            ? '룰북을 고르면 인물의 시트를 적을 수 있습니다. 능력치는 룰북이 정합니다.'
            : '이 시트는 붙인 로어북의 인물을 가리키지 않아 테이블에서 쓰이지 않습니다. 지우거나, 그 인물이 있는 로어북을 다시 붙이세요.'}
        </p>
        <div className="actions">{clearButton}</div>
      </div>
    );
  }
  return <NpcFields scenario={scenario} rules={rules} items={items} entryId={row.id} npc={npc} saving={saving} done={done} clearButton={clearButton} />;
}

type FieldsProps = {
  scenario: ScenarioDetail;
  rules: Ruleset;
  items: EntryChoice[];
  entryId: string;
  npc: NpcSheet | undefined;
  saving: ReturnType<typeof useScenarioSave>;
  done: () => void;
  clearButton: ReactNode;
};

function NpcFields({ scenario, rules, items, entryId, npc, saving, done, clearButton }: FieldsProps) {
  const [draft, setDraft] = useState<NpcDraft>(() => npcDraft(npc, rules));
  const hints = npcHints(draft, rules, scenario.items);
  const blocked = hasNpcHints(hints);

  function update(changes: Partial<NpcDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    if (await saving.save({ npc_sheets: withNpcSheet(scenario.npc_sheets, toNpcSheet(entryId, draft, rules)) })) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="인물 시트">
      <ProblemNotice problem={saving.problem} />
      <SheetFields
        legend="시트"
        rules={rules}
        draft={draft.sheet}
        hints={hints.sheet}
        onChange={(sheet) => update({ sheet })}
        note="인물 시트는 비울 수 없습니다. 숫자를 주지 않으려면 시트를 지우세요(기본 인물 시트를 받습니다)."
      />
      {hints.sheet.sheet ? <p className="ui-field__error">{hints.sheet.sheet}</p> : null}
      <div className="scenario-players__row">
        <SelectField label="처음 태도" value={draft.attitude} onChange={(event) => update({ attitude: event.target.value as NpcAttitude })} hint="테이블에서는 엔진이 바꿉니다.">
          {ATTITUDE_VALUES.map((attitude) => (
            <option key={attitude} value={attitude}>
              {attitudeLabel(attitude)}
            </option>
          ))}
        </SelectField>
        <SelectField label="훔치다 들키면" value={draft.onCaught} onChange={(event) => update({ onCaught: event.target.value as NpcCaught })}>
          {Object.entries(CAUGHT_LABELS).map(([caught, label]) => (
            <option key={caught} value={caught}>
              {label}
            </option>
          ))}
        </SelectField>
      </div>
      <Checkbox label="둔하다" description="훔치기가 쉬워집니다(룰북의 훔치기 규칙)." checked={draft.dull} onChange={(event) => update({ dull: event.target.checked })} />
      <Checkbox
        label="상인이다"
        description={`소지품 가운데 값이 있는 물건을 팔고, 값이 있는 물건을 사 줍니다. 소지품의 개수가 재고입니다.${scenario.currency ? '' : ' 화폐가 없으면 게시 점검이 알립니다.'}`}
        checked={draft.merchant}
        onChange={(event) => update({ merchant: event.target.checked })}
      />
      <fieldset className="scenario-choices">
        <legend>장비(착용한 물건)</legend>
        <StacksEditor
          label="장비"
          drafts={draft.equipment}
          onChange={(equipment) => update({ equipment })}
          entries={items}
          itemRules={scenario.items}
          rules={rules}
          hints={hints.equipment}
          max={MAX_CARRIED_EQUIPMENT}
          chance
          wearHint="착용한 칸(그 물건의 규칙이 정한 칸에서, 차지하는 칸의 수만큼)"
        />
      </fieldset>
      <fieldset className="scenario-choices">
        <legend>소지품</legend>
        <StacksEditor
          label="소지품"
          drafts={draft.inventory}
          onChange={(inventory) => update({ inventory })}
          entries={items}
          itemRules={scenario.items}
          rules={rules}
          hints={hints.inventory}
          max={MAX_CARRIED_INVENTORY}
          wear={false}
          chance
        />
      </fieldset>
      <p className="ui-field__hint">떨어질 확률은 처음 쓰러졌을 때 그 줄이 떨어질 확률입니다. 줄마다 따로 굴립니다.</p>
      <fieldset className="scenario-choices">
        <legend>공격</legend>
        <AttacksEditor
          drafts={draft.attacks}
          onChange={(attacks) => update({ attacks })}
          rules={rules}
          equipment={draft.equipment.map((line) => line.entryId)}
          entries={items}
          itemRules={scenario.items}
          hints={hints.attacks}
        />
      </fieldset>
      {blocked ? <Notice tone="error">고칠 칸이 있어 저장하지 않습니다.</Notice> : null}
      <div className="actions">
        <Button type="submit" busy={saving.busy} disabled={blocked}>
          저장
        </Button>
        {clearButton}
      </div>
    </form>
  );
}
