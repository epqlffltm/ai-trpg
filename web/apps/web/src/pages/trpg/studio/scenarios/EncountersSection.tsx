// web/apps/web/src/pages/trpg/studio/scenarios/EncountersSection.tsx
// 조우(B9 몬스터 탭). 장소마다 몬스터 몇 마리와 기습. 줄마다 "지하 묘지 · 구울 ×3 · 몬스터가 매복".
// 더하기와 고치기는 창에서, 지우기는 한 번 더 묻는다. 창의 저장이 조우 목록을 통째로 바로 보낸다.
// 몬스터는 시트를 적은 것만 고를 수 있다. 장소는 붙인 로어북의 장소 항목이고, 맵의 장소여야 한다(게시 점검이 본다).
// 순찰 경로(#254)는 처음 자리에서 돌 장소들이다. 줄마다 고르고 뺀다(PatrolFields).

import { Button, Dialog, SelectField, TextField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent } from 'react';
import type { ScenarioDetail, Surprise } from '../../../../api/types';
import { ConfirmButton } from '../../../../components/ConfirmButton';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import {
  ENCOUNTER_MAX_COUNT,
  encounterDraft,
  encounterHints,
  encounterLine,
  MAX_ENCOUNTERS,
  PATROL_MAX_PLACES,
  SURPRISE_VALUES,
  surpriseLabel,
  toEncounter,
  withEncounter,
  withoutEncounter,
  withPatrolPlace,
  type EncounterDraft,
} from './encountersForm';
import { mapPlaces } from './placesForm';
import type { MonsterChoice } from './useBestiaryMonsters';
import type { EntryChoice } from './useLoreEntries';
import { useScenarioSave } from './useScenarioSave';

type Props = {
  scenario: ScenarioDetail;
  places: EntryChoice[];
  monsters: MonsterChoice[];
  placeName: (id: string) => string;
  monsterName: (id: string) => string;
};

export function EncountersSection({ scenario, places, monsters, placeName, monsterName }: Props) {
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const removing = useScenarioSave(scenario.id);
  const encounters = scenario.encounters;
  const ready = scenario.monster_sheets.length > 0 && places.length > 0;
  return (
    <section className="page-section" aria-labelledby="encounters-heading">
      <h2 id="encounters-heading">
        조우{' '}
        <span className="hint">
          ({encounters.length} / {MAX_ENCOUNTERS})
        </span>
      </h2>
      <p className="hint">맵의 장소에 몬스터를 놓습니다. 시트를 적은 몬스터만 놓을 수 있고, 네임드는 판 전체에 한 마리입니다. 창에서 저장하면 바로 저장됩니다.</p>
      {!scenario.start_place ? <p className="hint">조우는 맵이 있어야 합니다. 지도 탭에서 시작 장소를 정하세요.</p> : null}
      <p>
        <Button variant="secondary" disabled={encounters.length >= MAX_ENCOUNTERS || !ready} onClick={() => setEditing('new')}>
          조우 더하기
        </Button>
      </p>
      {encounters.length === 0 ? <p className="hint">아직 조우가 없습니다.</p> : null}
      <ul className="plain-list studio-list" aria-label="조우">
        {encounters.map((encounter, at) => {
          const name = `${placeName(encounter.place_id)}의 ${monsterName(encounter.monster_id)}`;
          return (
            <li key={`${encounter.place_id}:${encounter.monster_id}`} className="studio-list__item studio-item">
              <div className="studio-list__description">{encounterLine(encounter, placeName, monsterName)}</div>
              <span className="action-chips">
                <Button variant="quiet" aria-label={`${name} 조우 고치기`} onClick={() => setEditing(at)}>
                  고치기
                </Button>
                <ConfirmButton
                  label="지우기"
                  ariaLabel={`${name} 조우 지우기`}
                  title="조우 지우기"
                  confirm="지우기"
                  busy={removing.busy}
                  problem={removing.problem}
                  onConfirm={async () => (await removing.save({ encounters: withoutEncounter(encounters, at) })) !== null}
                >
                  <p>{encounterLine(encounter, placeName, monsterName)}</p>
                </ConfirmButton>
              </span>
            </li>
          );
        })}
      </ul>
      <Dialog title={editing === 'new' ? '조우 더하기' : '조우 고치기'} open={editing !== null} onClose={close}>
        {editing !== null ? (
          <EncounterForm scenario={scenario} places={places} monsters={monsters} monsterName={monsterName} at={editing === 'new' ? null : editing} done={close} />
        ) : null}
      </Dialog>
    </section>
  );
}

type FormProps = {
  scenario: ScenarioDetail;
  places: EntryChoice[];
  monsters: MonsterChoice[];
  monsterName: (id: string) => string;
  at: number | null;
  done: () => void;
};

function EncounterForm({ scenario, places, monsters, monsterName, at, done }: FormProps) {
  const original = at === null ? null : (scenario.encounters[at] ?? null);
  const [draft, setDraft] = useState<EncounterDraft>(() => encounterDraft(original));
  const saving = useScenarioSave(scenario.id);
  const hints = encounterHints(draft, scenario.encounters, at, monsters);
  const blocked = Object.keys(hints).length > 0;
  const onMap = mapPlaces(scenario);
  const sheeted = scenario.monster_sheets.map((sheet) => sheet.monster_id);

  function update(changes: Partial<EncounterDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    if (await saving.save({ encounters: withEncounter(scenario.encounters, at, toEncounter(draft)) })) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="조우">
      <ProblemNotice problem={saving.problem} />
      <SelectField label="장소" value={draft.place} onChange={(event) => update({ place: event.target.value })} error={draft.place === '' ? undefined : hints.place}>
        {draft.place === '' ? <option value="">고르기</option> : null}
        {draft.place !== '' && !places.some((place) => place.id === draft.place) ? <option value={draft.place}>(붙인 로어북에 없는 장소)</option> : null}
        {places.map((place) => (
          <option key={place.id} value={place.id}>
            {place.name}
            {onMap.has(place.id) ? '' : '(맵 밖)'}
          </option>
        ))}
      </SelectField>
      <SelectField label="몬스터" value={draft.monster} onChange={(event) => update({ monster: event.target.value })} error={draft.monster === '' ? undefined : hints.monster}>
        {draft.monster === '' ? <option value="">고르기</option> : null}
        {draft.monster !== '' && !sheeted.includes(draft.monster) ? <option value={draft.monster}>{monsterName(draft.monster)}(시트 없음)</option> : null}
        {sheeted.map((id) => (
          <option key={id} value={id}>
            {monsterName(id)}
            {monsters.find((monster) => monster.id === id)?.unique ? '(네임드)' : ''}
          </option>
        ))}
      </SelectField>
      <TextField label={`마리 수(1~${ENCOUNTER_MAX_COUNT})`} inputMode="numeric" value={draft.count} onChange={(event) => update({ count: event.target.value })} error={hints.count} />
      <SelectField label="기습" value={draft.surprise} onChange={(event) => update({ surprise: event.target.value as Surprise })}>
        {SURPRISE_VALUES.map((surprise) => (
          <option key={surprise} value={surprise}>
            {surpriseLabel(surprise)}
          </option>
        ))}
      </SelectField>
      <PatrolFields places={places} patrol={draft.patrol} error={hints.patrol} onChange={(patrol) => update({ patrol })} />
      <div className="actions">
        <Button type="submit" busy={saving.busy} disabled={blocked}>
          {at === null ? '더하기' : '저장'}
        </Button>
      </div>
    </form>
  );
}

type PatrolProps = {
  places: EntryChoice[];
  patrol: string[];
  error: string | undefined;
  onChange: (patrol: string[]) => void;
};

/** 순찰 경로(#254). 처음 자리에서 이 장소들을 차례로 돌고 처음 자리로 돌아온다. 비우면 순찰하지 않는다 */
function PatrolFields({ places, patrol, error, onChange }: PatrolProps) {
  return (
    <fieldset className="scenario-choices">
      <legend>순찰 경로(선택)</legend>
      <p className="ui-field__hint">
        싸우지 않을 때 처음 자리에서 이 장소들을 차례로 돌고 처음 자리로 돌아옵니다. 장소끼리 이웃하지 않아도 가장 짧은 길로 한 칸씩 갑니다. 사냥이 순찰보다
        먼저입니다.
      </p>
      {patrol.map((place, index) => (
        <div key={index} className="ability-grid">
          <SelectField label={`순찰 ${index + 1}`} value={place} onChange={(event) => onChange(withPatrolPlace(patrol, index, event.target.value))}>
            {place === '' ? <option value="">고르기</option> : null}
            {place !== '' && !places.some((one) => one.id === place) ? <option value={place}>(붙인 로어북에 없는 장소)</option> : null}
            {places.map((one) => (
              <option key={one.id} value={one.id}>
                {one.name}
              </option>
            ))}
          </SelectField>
          <Button type="button" variant="secondary" onClick={() => onChange(withPatrolPlace(patrol, index, null))}>
            순찰 {index + 1} 빼기
          </Button>
        </div>
      ))}
      {error ? <p className="ui-field__error">{error}</p> : null}
      <Button type="button" variant="secondary" disabled={patrol.length >= PATROL_MAX_PLACES} onClick={() => onChange(withPatrolPlace(patrol, null, null))}>
        순찰할 곳 더하기
      </Button>
    </fieldset>
  );
}
