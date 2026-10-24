// web/apps/web/src/pages/trpg/studio/scenarios/WandersSection.tsx
// 무작위 조우 표(B9 몬스터 탭, #283). 길을 와서 닿은 장소나 길게 쉰 장소에서 엔진이 한 번 굴리는 표다.
// 줄마다 "지하 묘지 · 밤, 새벽 · 30% · 구울 ×3(67%), 리치(33%)". 더하기와 고치기는 창에서, 지우기는 한 번 더 묻는다.
// 창의 저장이 표의 목록을 통째로 바로 보낸다. 검사는 wandersForm.ts. 몬스터는 시트를 적은 것만 고른다.

import { Button, Checkbox, Dialog, SelectField, TextField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent } from 'react';
import type { ScenarioDetail, Surprise } from '../../../../api/types';
import { ConfirmButton } from '../../../../components/ConfirmButton';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { wholeNumber } from '../rulebooks/rulebookForm';
import { ENCOUNTER_MAX_COUNT, SURPRISE_VALUES, surpriseLabel } from './encountersForm';
import { mapPlaces } from './placesForm';
import type { EntryChoice } from './useLoreEntries';
import { useScenarioSave } from './useScenarioSave';
import {
  DAY_TIMES,
  dayTimeLabel,
  hasWanderHints,
  MAX_WANDERS,
  newWanderMonster,
  toggleTime,
  toWander,
  WANDER_MAX_MONSTERS,
  WANDER_MAX_WEIGHT,
  wanderDraft,
  wanderHints,
  wanderLine,
  weightShare,
  withoutWander,
  withWander,
  type WanderDraft,
  type WanderMonsterDraft,
} from './wandersForm';

type Props = {
  scenario: ScenarioDetail;
  places: EntryChoice[];
  placeName: (id: string) => string;
  monsterName: (id: string) => string;
};

export function WandersSection({ scenario, places, placeName, monsterName }: Props) {
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const removing = useScenarioSave(scenario.id);
  const tables = scenario.wanders;
  return (
    <section className="page-section" aria-labelledby="wanders-heading">
      <h2 id="wanders-heading">
        무작위 조우 표{' '}
        <span className="hint">
          ({tables.length} / {MAX_WANDERS})
        </span>
      </h2>
      <p className="hint">
        걸리는 시간이 있는 길을 와서 닿은 장소나 길게 쉰 장소에서 엔진이 한 번 굴립니다. 확률만큼 조우가 나고, 몬스터 줄 하나를 몫대로 뽑습니다. 쉬는 중이면 몬스터가 기습합니다. 장소를 비운 기본 표는 표가 없는 장소에서 씁니다. 창에서 저장하면 바로 저장됩니다.
      </p>
      {!scenario.start_place ? <p className="hint">무작위 조우는 맵이 있어야 합니다. 지도 탭에서 시작 장소를 정하세요.</p> : null}
      <p>
        <Button variant="secondary" disabled={tables.length >= MAX_WANDERS} onClick={() => setEditing('new')}>
          표 더하기
        </Button>
      </p>
      {tables.length === 0 ? <p className="hint">아직 표가 없습니다. 표가 없으면 무작위 조우가 나지 않습니다.</p> : null}
      <ul className="plain-list studio-list" aria-label="무작위 조우 표">
        {tables.map((table, at) => {
          const name = `${table.place_id ? placeName(table.place_id) : '기본 표'} ${table.times.length === 0 ? '언제나' : table.times.map(dayTimeLabel).join('·')}`;
          return (
            <li key={`${table.place_id ?? 'default'}:${table.times.join(',')}`} className="studio-list__item studio-item">
              <div className="studio-list__description">{wanderLine(table, placeName, monsterName)}</div>
              <span className="action-chips">
                <Button variant="quiet" aria-label={`${name} 표 고치기`} onClick={() => setEditing(at)}>
                  고치기
                </Button>
                <ConfirmButton
                  label="지우기"
                  ariaLabel={`${name} 표 지우기`}
                  title="무작위 조우 표 지우기"
                  confirm="지우기"
                  busy={removing.busy}
                  problem={removing.problem}
                  onConfirm={async () => (await removing.save({ wanders: withoutWander(tables, at) })) !== null}
                >
                  <p>{wanderLine(table, placeName, monsterName)}</p>
                </ConfirmButton>
              </span>
            </li>
          );
        })}
      </ul>
      <Dialog title={editing === 'new' ? '무작위 조우 표 더하기' : '무작위 조우 표 고치기'} open={editing !== null} onClose={close}>
        {editing !== null ? <WanderForm scenario={scenario} places={places} monsterName={monsterName} at={editing === 'new' ? null : editing} done={close} /> : null}
      </Dialog>
    </section>
  );
}

type FormProps = {
  scenario: ScenarioDetail;
  places: EntryChoice[];
  monsterName: (id: string) => string;
  at: number | null;
  done: () => void;
};

function WanderForm({ scenario, places, monsterName, at, done }: FormProps) {
  const original = at === null ? null : (scenario.wanders[at] ?? null);
  const [draft, setDraft] = useState<WanderDraft>(() => wanderDraft(original));
  const saving = useScenarioSave(scenario.id);
  const sheeted = scenario.monster_sheets.map((sheet) => sheet.monster_id);
  const hints = wanderHints(draft, scenario.wanders, at, sheeted);
  const onMap = mapPlaces(scenario);
  const safe = wholeNumber(draft.chance, 0, 100) === 0;

  function update(changes: Partial<WanderDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (hasWanderHints(hints)) return;
    if (await saving.save({ wanders: withWander(scenario.wanders, at, toWander(draft)) })) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="무작위 조우 표">
      <ProblemNotice problem={saving.problem} />
      <SelectField label="장소" value={draft.place} onChange={(event) => update({ place: event.target.value })} hint="비우면 판의 기본 표입니다. 표를 하나도 적지 않은 장소에서 씁니다.">
        <option value="">기본 표(표가 없는 장소)</option>
        {draft.place !== '' && !places.some((place) => place.id === draft.place) ? <option value={draft.place}>(붙인 로어북에 없는 장소)</option> : null}
        {places.map((place) => (
          <option key={place.id} value={place.id}>
            {place.name}
            {onMap.has(place.id) ? '' : '(맵 밖)'}
          </option>
        ))}
      </SelectField>
      <fieldset className="scenario-choices">
        <legend>하루의 때</legend>
        <p className="ui-field__hint">비우면 언제나 씁니다. 한 장소의 표들은 때가 겹치지 못합니다. 때가 맞는 표가 없으면 조우가 없습니다.</p>
        <div className="choice-list choice-list--inline">
          {DAY_TIMES.map((time) => (
            <Checkbox key={time} label={dayTimeLabel(time)} checked={draft.times.includes(time)} onChange={() => update({ times: toggleTime(draft.times, time) })} />
          ))}
        </div>
        {hints.fields.times ? <p className="ui-field__error">{hints.fields.times}</p> : null}
      </fieldset>
      <TextField label="조우가 날 확률(%, 0~100)" inputMode="numeric" value={draft.chance} onChange={(event) => update({ chance: event.target.value })} error={hints.fields.chance} />
      {safe ? (
        <p className="hint">확률이 0 이면 안전한 곳입니다(마을처럼). 몬스터를 적지 않습니다.</p>
      ) : (
        <WanderMonsters rows={draft.monsters} sheeted={sheeted} monsterName={monsterName} hints={hints.monsters} error={hints.fields.monsters} onChange={(monsters) => update({ monsters })} />
      )}
      <div className="actions">
        <Button type="submit" busy={saving.busy} disabled={hasWanderHints(hints)}>
          {at === null ? '더하기' : '저장'}
        </Button>
      </div>
    </form>
  );
}

type MonstersProps = {
  rows: WanderMonsterDraft[];
  sheeted: string[];
  monsterName: (id: string) => string;
  hints: Record<number, string>;
  error: string | undefined;
  onChange: (rows: WanderMonsterDraft[]) => void;
};

/** 표의 몬스터 줄들. 줄마다 몬스터, 마리 수, 몫(뽑힐 비율을 함께 보인다), 기습 */
function WanderMonsters({ rows, sheeted, monsterName, hints, error, onChange }: MonstersProps) {
  const total = rows.reduce((sum, row) => sum + (wholeNumber(row.weight, 1, WANDER_MAX_WEIGHT) ?? 0), 0);
  const change = (index: number, changes: Partial<WanderMonsterDraft>) => onChange(rows.map((row, at) => (at === index ? { ...row, ...changes } : row)));
  return (
    <fieldset className="scenario-choices">
      <legend>나올 몬스터</legend>
      <p className="ui-field__hint">조우가 나면 줄 하나를 몫대로 뽑습니다. 시트를 적은 몬스터만 고를 수 있습니다.</p>
      {rows.map((row, index) => (
        <fieldset key={index} className="scenario-choices">
          <legend>몬스터 {index + 1}</legend>
          <SelectField label="몬스터" value={row.monster} onChange={(event) => change(index, { monster: event.target.value })} error={hints[index]}>
            <option value="">고르기</option>
            {row.monster !== '' && !sheeted.includes(row.monster) ? <option value={row.monster}>{monsterName(row.monster)}(시트 없음)</option> : null}
            {sheeted.map((id) => (
              <option key={id} value={id}>
                {monsterName(id)}
              </option>
            ))}
          </SelectField>
          <div className="scenario-players__row">
            <TextField label={`마리 수(1~${ENCOUNTER_MAX_COUNT})`} inputMode="numeric" value={row.count} onChange={(event) => change(index, { count: event.target.value })} />
            <TextField label={`몫(1~${WANDER_MAX_WEIGHT})`} inputMode="numeric" value={row.weight} onChange={(event) => change(index, { weight: event.target.value })} />
          </div>
          <p className="ui-field__hint">뽑힐 비율: {weightShare(wholeNumber(row.weight, 1, WANDER_MAX_WEIGHT) ?? 0, total) || '-'}</p>
          <SelectField label="기습" value={row.surprise} onChange={(event) => change(index, { surprise: event.target.value as Surprise })}>
            {SURPRISE_VALUES.map((surprise) => (
              <option key={surprise} value={surprise}>
                {surpriseLabel(surprise)}
              </option>
            ))}
          </SelectField>
          <Button variant="quiet" aria-label={`몬스터 ${index + 1} 지우기`} onClick={() => onChange(rows.filter((_, at) => at !== index))}>
            지우기
          </Button>
        </fieldset>
      ))}
      {error ? <p className="ui-field__error">{error}</p> : null}
      <p>
        <Button variant="secondary" disabled={rows.length >= WANDER_MAX_MONSTERS} onClick={() => onChange([...rows, newWanderMonster()])}>
          몬스터 더하기
        </Button>{' '}
        <span className="hint">
          {rows.length} / {WANDER_MAX_MONSTERS}
        </span>
      </p>
    </fieldset>
  );
}
