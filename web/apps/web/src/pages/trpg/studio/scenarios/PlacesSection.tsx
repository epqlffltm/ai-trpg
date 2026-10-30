// web/apps/web/src/pages/trpg/studio/scenarios/PlacesSection.tsx
// 지도 탭의 장소(B9). 붙인 로어북의 장소 항목을 모두 늘어놓고 줄마다 "시작 · 길 3 · 커버 5 · 인물 2"를 보인다.
// 줄을 고치면 창이 열리고 명소인지, 커버, 처음 있는 인물, 놓인 물건, 미리 놓인 덫(#806 ②)을 고친다.
// 창의 저장이 모두를 함께 바로 보낸다.
// 지도가 가리키지만 붙인 로어북에 없는 장소도 줄로 남겨 비울 수 있게 한다.

import { Button, Checkbox, Dialog, TextField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent } from 'react';
import type { Ruleset, ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { PlaceItemsEditor } from './PlaceItemsEditor';
import { PlaceTrapsEditor } from './PlaceTrapsEditor';
import {
  applyPlace,
  mapPlaces,
  personElsewhere,
  placeDraft,
  placeHints,
  placeLine,
  presetTraps,
  togglePerson,
  trapEntries,
  type PlaceDraft,
} from './placesForm';
import type { EntryChoice } from './useLoreEntries';
import { useScenarioSave } from './useScenarioSave';

type Props = {
  scenario: ScenarioDetail;
  rules: Ruleset | null;
  places: EntryChoice[];
  people: EntryChoice[];
  items: EntryChoice[];
  nameOf: (placeId: string) => string;
};

/** 장소 항목들과, 지도·커버·인물의 자리가 가리키지만 항목이 없는 장소들 */
function placeIds(scenario: ScenarioDetail, places: EntryChoice[]): string[] {
  const listed = places.map((place) => place.id);
  const referred = [
    ...mapPlaces(scenario),
    ...scenario.covers.map((rule) => rule.place_id),
    ...scenario.npc_places.map((place) => place.place_id),
    ...scenario.place_items.map((item) => item.place_id),
    ...presetTraps(scenario).map((trap) => trap.place_id),
  ];
  return [...listed, ...new Set(referred.filter((id) => !listed.includes(id)))];
}

export function PlacesSection({ scenario, rules, places, people, items, nameOf }: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const ids = placeIds(scenario, places);
  return (
    <section className="page-section" aria-labelledby="places-heading">
      <h2 id="places-heading">장소</h2>
      <p className="hint">
        맵의 장소는 시작 장소, 길의 끝, 명소입니다. 길이 없는 장소를 맵에 두려면 명소로 둡니다. 맵 밖의 장소에는 아무도 설 수 없습니다. 창에서 저장하면 바로 저장됩니다.
      </p>
      {ids.length === 0 ? <p className="hint">붙인 로어북에 장소 항목이 없습니다. 로어북에 종류가 장소인 항목을 더하세요.</p> : null}
      <ul className="plain-list studio-list" aria-label="장소">
        {ids.map((id) => (
          <li key={id} className="studio-list__item studio-item">
            <div>
              <strong>{nameOf(id)}</strong>
              <div className="studio-list__description hint">{placeLine(scenario, id) || '아무것도 없음'}</div>
            </div>
            <Button variant="quiet" aria-label={`${nameOf(id)} 고치기`} onClick={() => setEditing(id)}>
              고치기
            </Button>
          </li>
        ))}
      </ul>
      <Dialog title={editing ? `장소: ${nameOf(editing)}` : '장소'} open={editing !== null} onClose={close}>
        {editing ? <PlaceForm scenario={scenario} rules={rules} placeId={editing} people={people} items={items} nameOf={nameOf} done={close} /> : null}
      </Dialog>
    </section>
  );
}

type FormProps = Omit<Props, 'places'> & { placeId: string; done: () => void };

function PlaceForm({ scenario, rules, placeId, people, items, nameOf, done }: FormProps) {
  const [draft, setDraft] = useState<PlaceDraft>(() => placeDraft(scenario, placeId));
  const saving = useScenarioSave(scenario.id);
  const hints = placeHints(draft);
  const blocked = Object.keys(hints).length > 0;
  const routes = scenario.routes.some((route) => route.from_place === placeId || route.to_place === placeId);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    if (await saving.save(applyPlace(scenario, placeId, draft))) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="장소">
      <ProblemNotice problem={saving.problem} />
      <Checkbox
        label="명소로 둔다"
        description={routes || scenario.start_place === placeId ? '길이나 시작 장소라 이미 맵에 있습니다. 명소로 두어도 같습니다.' : '길이 없어도 맵에 둡니다. 사건으로 옮겨 가는 곳에 씁니다.'}
        checked={draft.landmark}
        onChange={(event) => setDraft((current) => ({ ...current, landmark: event.target.checked }))}
      />
      <TextField
        label="커버(선택, 1~10)"
        inputMode="numeric"
        value={draft.cover}
        onChange={(event) => setDraft((current) => ({ ...current, cover: event.target.value }))}
        error={hints.cover}
      />
      <p className="ui-field__hint">숨을 곳이 얼마나 좋은지입니다. 세이브 방식의 룰북에서 이곳에 선 사람이 엄폐하면 이 값으로 커버 세이브를 받습니다.</p>
      <fieldset className="scenario-choices">
        <legend>처음 이곳에 있는 인물</legend>
        <p className="ui-field__hint">자리가 있는 인물은 이곳에 선 캐릭터의 장면에만 나오고, 같은 장소에서만 겨눕니다. 인물 하나는 한 곳에만 있습니다.</p>
        {people.length === 0 ? <p className="hint">붙인 로어북에 인물 항목이 없습니다.</p> : null}
        {people.map((person) => {
          const elsewhere = personElsewhere(scenario, person.id, placeId);
          return (
            <Checkbox
              key={person.id}
              label={person.name}
              description={elsewhere && !draft.people.includes(person.id) ? `지금 ${nameOf(elsewhere)}에 있습니다. 고르면 이곳으로 옮깁니다.` : undefined}
              checked={draft.people.includes(person.id)}
              onChange={() => setDraft((current) => ({ ...current, people: togglePerson(current.people, person.id) }))}
            />
          );
        })}
      </fieldset>
      <fieldset className="scenario-choices">
        <legend>놓인 물건</legend>
        <p className="ui-field__hint">보이는 물건은 이곳에 서 본 뒤 줍기로 가져갑니다. 숨긴 물건은 찾는 판정에 성공한 사람이 바로 갖습니다.</p>
        <PlaceItemsEditor
          drafts={draft.items}
          onChange={(placeItems) => setDraft((current) => ({ ...current, items: placeItems }))}
          entries={items}
          rules={rules}
          hints={hints}
          others={scenario.place_items.filter((item) => item.place_id !== placeId).length}
        />
      </fieldset>
      <fieldset className="scenario-choices">
        <legend>미리 놓인 덫</legend>
        <p className="ui-field__hint">
          숨긴 덫은 이곳에 들어오는 캐릭터가 피하는 판정을 굴리고, 찾기로 찾아낼 수 있습니다. 처음부터 아는 덫은 맵에 보이고 밟지 않으며 해제할 수 있습니다. 덫 물건은 물건 탭에서 덫을 적은
          것만 고릅니다.
        </p>
        <PlaceTrapsEditor
          drafts={draft.traps}
          onChange={(traps) => setDraft((current) => ({ ...current, traps }))}
          entries={trapEntries(scenario, items)}
          hints={hints}
          others={presetTraps(scenario).filter((trap) => trap.place_id !== placeId).length}
        />
      </fieldset>
      <div className="actions">
        <Button type="submit" busy={saving.busy} disabled={blocked}>
          저장
        </Button>
      </div>
    </form>
  );
}
