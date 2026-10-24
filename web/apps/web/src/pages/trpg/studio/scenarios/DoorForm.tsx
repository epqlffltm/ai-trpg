// web/apps/web/src/pages/trpg/studio/scenarios/DoorForm.tsx
// 길 하나의 문(B9 지도, #281). 넘기 판정, 자물쇠(열쇠, 처음에 잠김, 따기와 도구), 빗장(어느 쪽, 처음에 걸림), 부수기, 고치기(도구).
// 켜고 끄는 상자마다 칸이 열린다. 창의 저장이 길 목록을 통째로 바로 보내되 이 길의 문만 바꾼다. 검사는 doorForm.ts.

import { Button, Checkbox, SelectField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import type { Ruleset, ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { CheckSelects } from './CheckSelects';
import { doorDraft, doorHints, withDoor, type DoorDraft } from './doorForm';
import { ItemSelect } from './ItemSelect';
import type { EntryChoice } from './useLoreEntries';
import { useScenarioSave } from './useScenarioSave';

type Props = {
  scenario: ScenarioDetail;
  rules: Ruleset | null;
  /** 열쇠와 도구로 고를 물건 항목 */
  items: EntryChoice[];
  at: number;
  nameOf: (placeId: string) => string;
  done: () => void;
};

export function DoorForm({ scenario, rules, items, at, nameOf, done }: Props) {
  const route = scenario.routes[at];
  const [draft, setDraft] = useState<DoorDraft | null>(() => (route ? doorDraft(route) : null));
  const saving = useScenarioSave(scenario.id);
  if (!route || !draft) return <p>이 길을 찾을 수 없습니다.</p>;
  const hints = doorHints(draft, scenario.routes, at, scenario.items.flatMap((rule) => (rule.lock ? [rule.lock.key] : [])));
  const blocked = Object.keys(hints).length > 0;

  function update<K extends keyof DoorDraft>(part: K, changes: Partial<DoorDraft[K]>) {
    setDraft((current) => (current ? { ...current, [part]: { ...current[part], ...changes } } : current));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked || !draft) return;
    if (await saving.save({ routes: withDoor(scenario.routes, at, draft) })) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="길의 문">
      <ProblemNotice problem={saving.problem} />
      <p className="hint">
        {nameOf(route.from_place)} {route.two_way ? '↔' : '→'} {nameOf(route.to_place)}
      </p>
      <fieldset className="scenario-choices">
        <legend>넘기 판정</legend>
        <Checkbox
          label="지날 때마다 판정한다"
          description="절벽 오르기, 급류 헤엄치기. 실패하면 가지 못하고 그 자리에 남습니다."
          checked={draft.cross.on}
          onChange={(event) => update('cross', { on: event.target.checked })}
        />
        {draft.cross.on ? (
          <CheckSelects
            label="넘기 판정"
            rules={rules}
            ability={draft.cross.ability}
            difficulty={draft.cross.difficulty}
            harm={draft.cross.harm}
            onChange={(changes) => update('cross', changes)}
            error={hints.cross}
          />
        ) : null}
      </fieldset>
      <fieldset className="scenario-choices">
        <legend>자물쇠</legend>
        <Checkbox
          label="자물쇠가 있다"
          description="열쇠를 지닌 사람만 지나가며 엽니다. 열쇠는 쓰여도 없어지지 않습니다."
          checked={draft.lock.on}
          onChange={(event) => update('lock', { on: event.target.checked })}
        />
        {draft.lock.on ? (
          <>
            <ItemSelect label="열쇠" value={draft.lock.key} items={items} empty="고르기" onChange={(key) => update('lock', { key })} error={hints.lock} />
            <Checkbox label="처음에 잠겨 있다" checked={draft.lock.locked} onChange={(event) => update('lock', { locked: event.target.checked })} />
            <Checkbox label="열쇠 없이 딸 수 있다" checked={draft.pick.on} onChange={(event) => update('pick', { on: event.target.checked })} />
            {draft.pick.on ? (
              <>
                <CheckSelects
                  label="따기 판정"
                  rules={rules}
                  ability={draft.pick.ability}
                  difficulty={draft.pick.difficulty}
                  onChange={(changes) => update('pick', changes)}
                  error={hints.pick}
                />
                <ItemSelect label="따는 도구(선택)" value={draft.pick.tool} items={items} empty="도구 없이" onChange={(tool) => update('pick', { tool })} />
              </>
            ) : null}
          </>
        ) : null}
      </fieldset>
      <fieldset className="scenario-choices">
        <legend>빗장</legend>
        <Checkbox
          label="빗장이 있다"
          description="빗장 쪽에 선 사람만 열쇠 없이 걸고 풉니다. 걸려 있으면 반대쪽에서는 부수기로만 엽니다."
          checked={draft.bar.on}
          onChange={(event) => update('bar', { on: event.target.checked })}
        />
        {draft.bar.on ? (
          <>
            <SelectField label="빗장이 있는 쪽" value={draft.bar.side} onChange={(event) => update('bar', { side: event.target.value })} error={hints.bar}>
              {[route.from_place, route.to_place].map((place) => (
                <option key={place} value={place}>
                  {nameOf(place)}
                </option>
              ))}
            </SelectField>
            <Checkbox label="처음에 걸려 있다" checked={draft.bar.barred} onChange={(event) => update('bar', { barred: event.target.checked })} />
          </>
        ) : null}
      </fieldset>
      <fieldset className="scenario-choices">
        <legend>부수기</legend>
        <Checkbox
          label="문을 부술 수 있다"
          description="성공하면 자물쇠와 빗장이 부서져 열립니다. 자물쇠나 빗장이 있어야 합니다."
          checked={draft.force.on}
          disabled={!draft.lock.on && !draft.bar.on}
          onChange={(event) => update('force', { on: event.target.checked })}
        />
        {draft.force.on ? (
          <CheckSelects
            label="부수기 판정"
            rules={rules}
            ability={draft.force.ability}
            difficulty={draft.force.difficulty}
            onChange={(changes) => update('force', changes)}
            error={hints.force}
          />
        ) : null}
      </fieldset>
      <fieldset className="scenario-choices">
        <legend>고치기</legend>
        <Checkbox
          label="부서진 문을 고칠 수 있다"
          description="부서진 자물쇠와 빗장을 판정으로 고칩니다. 고친 문은 열린 채라 다시 막으려면 잠그기를 합니다. 자물쇠나 빗장이 있어야 합니다."
          checked={draft.repair.on}
          disabled={!draft.lock.on && !draft.bar.on}
          onChange={(event) => update('repair', { on: event.target.checked })}
        />
        {draft.repair.on ? (
          <>
            <CheckSelects
              label="고치기 판정"
              rules={rules}
              ability={draft.repair.ability}
              difficulty={draft.repair.difficulty}
              onChange={(changes) => update('repair', changes)}
              error={hints.repair}
            />
            <ItemSelect label="고치는 도구(선택)" value={draft.repair.tool} items={items} empty="도구 없이" onChange={(tool) => update('repair', { tool })} />
            <p className="ui-field__hint">도구를 고르면 그 물건을 지닌 사람만 고칩니다. 도구는 쓰여도 없어지지 않습니다.</p>
          </>
        ) : null}
      </fieldset>
      <div className="actions">
        <Button type="submit" busy={saving.busy} disabled={blocked}>
          저장
        </Button>
      </div>
    </form>
  );
}
