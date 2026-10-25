// web/apps/web/src/pages/trpg/studio/scenarios/MonsterSheetsSection.tsx
// 몬스터 시트(B9 몬스터 탭). 붙인 모음의 몬스터를 모두 늘어놓고, 줄마다 시트(없으면 "시트 없음")를 한 줄로 보인다.
// 시트를 적은 몬스터만 판에 들어가고 조우에 놓을 수 있다. 줄을 고치면 창이 열리고 창의 저장이 몬스터 시트 목록을 통째로 바로 보낸다.
// 시트 지우기는 그 몬스터를 판에서 뺀다. 붙인 모음에 없는 몬스터의 시트도 줄로 남겨 지울 수 있게 한다.
// 부상의 성질마다 면역과 약함을 고른다(#799). 언데드는 독, 만들어진 것은 독과 정신에 이미 면역이다(타입의 성질표).

import { Button, Checkbox, Dialog, Notice, TextField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent, type ReactNode } from 'react';
import type { MonsterSheet, Ruleset, ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { AttacksEditor } from './AttacksEditor';
import {
  hasMonsterHints,
  INJURY_NATURES,
  monsterDraft,
  monsterHints,
  monsterLine,
  toggledNature,
  toMonsterSheet,
  withMonsterSheet,
  withoutMonsterSheet,
  type InjuryNature,
  type MonsterDraft,
} from './monsterForm';
import { SheetFields } from './SheetFields';
import { MAX_CARRIED_EQUIPMENT, MAX_CARRIED_INVENTORY } from './stacksForm';
import { StacksEditor } from './StacksEditor';
import type { MonsterChoice } from './useBestiaryMonsters';
import type { EntryChoice } from './useLoreEntries';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail; rules: Ruleset | null; monsters: MonsterChoice[]; items: EntryChoice[] };

type Row = { id: string; name: string; unique: boolean; listed: boolean };

function rowsOf(monsters: MonsterChoice[], sheets: MonsterSheet[]): Row[] {
  const listed = monsters.map((monster) => ({ ...monster, listed: true }));
  const orphans = sheets
    .filter((sheet) => !monsters.some((monster) => monster.id === sheet.monster_id))
    .map((sheet) => ({ id: sheet.monster_id, name: '(붙인 모음에 없는 몬스터)', unique: false, listed: false }));
  return [...listed, ...orphans];
}

export function MonsterSheetsSection({ scenario, rules, monsters, items }: Props) {
  const [editing, setEditing] = useState<Row | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const rows = rowsOf(monsters, scenario.monster_sheets);
  return (
    <section className="page-section" aria-labelledby="monster-sheets-heading">
      <h2 id="monster-sheets-heading">몬스터 시트</h2>
      <p className="hint">붙인 몬스터 모음의 몬스터마다 숫자, 공격, 지닌 물건, 타고난 방어를 정합니다. 시트를 적은 몬스터만 이 시나리오에 나옵니다. 창에서 저장하면 바로 저장됩니다.</p>
      {rows.length === 0 ? <p className="hint">붙인 몬스터 모음에 몬스터가 없습니다.</p> : null}
      <ul className="plain-list studio-list" aria-label="몬스터 시트">
        {rows.map((row) => {
          const sheet = scenario.monster_sheets.find((one) => one.monster_id === row.id);
          return (
            <li key={row.id} className="studio-list__item studio-item">
              <div>
                <strong>{row.name}</strong> {row.unique ? <span className="hint">네임드</span> : null}
                <div className="studio-list__description hint">{sheet ? monsterLine(sheet, rules) : '시트 없음(이 시나리오에 나오지 않음)'}</div>
              </div>
              <Button variant="quiet" aria-label={`${row.name} 시트 고치기`} onClick={() => setEditing(row)}>
                고치기
              </Button>
            </li>
          );
        })}
      </ul>
      <Dialog title={editing ? `몬스터 시트: ${editing.name}` : '몬스터 시트'} open={editing !== null} onClose={close}>
        {editing ? <MonsterForm scenario={scenario} rules={rules} items={items} row={editing} done={close} /> : null}
      </Dialog>
    </section>
  );
}

type FormProps = { scenario: ScenarioDetail; rules: Ruleset | null; items: EntryChoice[]; row: Row; done: () => void };

function MonsterForm({ scenario, rules, items, row, done }: FormProps) {
  const sheet = scenario.monster_sheets.find((one) => one.monster_id === row.id);
  const saving = useScenarioSave(scenario.id);
  const used = scenario.encounters.some((encounter) => encounter.monster_id === row.id);

  async function clear() {
    if (await saving.save({ monster_sheets: withoutMonsterSheet(scenario.monster_sheets, row.id) })) done();
  }

  const clearButton = sheet ? (
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
            ? '룰북을 고르면 몬스터의 시트를 적을 수 있습니다. 능력치는 룰북이 정합니다.'
            : '이 시트는 붙인 모음의 몬스터를 가리키지 않아 테이블에서 쓰이지 않습니다. 지우거나, 그 몬스터가 있는 모음을 다시 붙이세요.'}
        </p>
        <div className="actions">{clearButton}</div>
      </div>
    );
  }
  return (
    <MonsterFields
      scenario={scenario}
      rules={rules}
      items={items}
      monsterId={row.id}
      sheet={sheet}
      used={used}
      saving={saving}
      done={done}
      clearButton={clearButton}
    />
  );
}

type FieldsProps = {
  scenario: ScenarioDetail;
  rules: Ruleset;
  items: EntryChoice[];
  monsterId: string;
  sheet: MonsterSheet | undefined;
  used: boolean;
  saving: ReturnType<typeof useScenarioSave>;
  done: () => void;
  clearButton: ReactNode;
};

function MonsterFields({ scenario, rules, items, monsterId, sheet, used, saving, done, clearButton }: FieldsProps) {
  const [draft, setDraft] = useState<MonsterDraft>(() => monsterDraft(sheet, rules));
  const hints = monsterHints(draft, rules, scenario.items);
  const blocked = hasMonsterHints(hints);

  function update(changes: Partial<MonsterDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    if (await saving.save({ monster_sheets: withMonsterSheet(scenario.monster_sheets, toMonsterSheet(monsterId, draft, rules)) })) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="몬스터 시트">
      <ProblemNotice problem={saving.problem} />
      {used ? <p className="hint">조우에 놓인 몬스터입니다. 시트를 지우면 그 조우가 게시 점검에 걸립니다.</p> : null}
      <SheetFields
        legend="시트"
        rules={rules}
        draft={draft.sheet}
        hints={hints.sheet}
        onChange={(next) => update({ sheet: next })}
        note="몬스터 시트는 비울 수 없습니다. 이 몬스터를 쓰지 않으려면 시트를 지우세요."
      />
      {hints.sheet.sheet ? <p className="ui-field__error">{hints.sheet.sheet}</p> : null}
      <Checkbox label="둔하다" description="훔치기가 쉬워집니다(룰북의 훔치기 규칙)." checked={draft.dull} onChange={(event) => update({ dull: event.target.checked })} />
      <fieldset className="scenario-choices">
        <legend>타고난 방어(선택, 1~10)</legend>
        <p className="ui-field__hint">가죽, 비늘, 껍데기. 부위마다 착용한 방어구의 방어에 더합니다. 불굴 세이브는 세이브 방식에서 관통을 무시하고 막습니다.</p>
        <div className="ability-grid">
          {rules.equipment_slots.map((slot) => (
            <TextField
              key={slot.key}
              label={slot.name}
              inputMode="numeric"
              value={draft.natural[slot.key] ?? ''}
              onChange={(event) => update({ natural: { ...draft.natural, [slot.key]: event.target.value } })}
              error={hints.armor[slot.key]}
            />
          ))}
          <TextField label="불굴 세이브" inputMode="numeric" value={draft.ward} onChange={(event) => update({ ward: event.target.value })} error={hints.armor.ward} />
        </div>
      </fieldset>
      <NatureFields draft={draft} error={hints.natures} onChange={update} />
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
      <p className="ui-field__hint">떨어질 확률은 그 마리가 쓰러졌을 때 줄마다 따로 굴립니다. 마리마다 지닌 것입니다.</p>
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

type NatureProps = { draft: MonsterDraft; error: string | null; onChange: (changes: Partial<MonsterDraft>) => void };

/** 부상의 성질마다 면역과 약함(#799). 룰북의 부상마다 성질이 적혀 있다 */
function NatureFields({ draft, error, onChange }: NatureProps) {
  const natures = Object.entries(INJURY_NATURES) as [InjuryNature, string][];
  return (
    <fieldset className="scenario-choices">
      <legend>부상의 면역과 약함(선택)</legend>
      <p className="ui-field__hint">
        면역인 성질의 부상은 입지 않고 노려 칠 수도 없습니다. 언데드는 독, 만들어진 것은 독과 정신에 이미 면역이고, 약함을 고르면 그 면역을 뺍니다.
      </p>
      {natures.map(([nature, label]) => (
        <div key={nature} className="ability-grid">
          <Checkbox
            label={`${label}에 면역`}
            checked={draft.immune.includes(nature)}
            onChange={(event) => onChange({ immune: toggledNature(draft.immune, nature, event.target.checked) })}
          />
          <Checkbox
            label={`${label}에 약함`}
            checked={draft.vulnerable.includes(nature)}
            onChange={(event) => onChange({ vulnerable: toggledNature(draft.vulnerable, nature, event.target.checked) })}
          />
        </div>
      ))}
      {error ? <p className="ui-field__error">{error}</p> : null}
    </fieldset>
  );
}
