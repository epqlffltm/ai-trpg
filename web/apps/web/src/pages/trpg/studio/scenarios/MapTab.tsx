// web/apps/web/src/pages/trpg/studio/scenarios/MapTab.tsx
// 시나리오의 지도 탭(B9). 탭의 저장: 시작 장소. 창에서 바로 저장: 장소(명소, 커버, 인물의 자리, 놓인 물건, PlacesSection)와
// 길(두 끝·보임·시간, 그리고 길의 문, RoutesSection).
// 지도는 좌표 없이 장소와 길뿐이라 그림 없이 목록 둘로 보인다. 장소는 저장된 로어북들의 장소 항목이다.

import { Button, Notice, SelectField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { ScenarioDetail } from '../../../../api/types';
import { placeNameOf } from './placesForm';
import { PlacesSection } from './PlacesSection';
import { RoutesSection } from './RoutesSection';
import { ScenarioForm } from './ScenarioForm';
import type { ScenarioTab } from './scenarioTabs';
import { useLoreEntries, type EntryChoice } from './useLoreEntries';
import { useScenarioRules } from './useScenarioRules';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail; goTo: (tab: ScenarioTab) => void };

export function MapTab({ scenario, goTo }: Props) {
  const { rules, pending } = useScenarioRules(scenario);
  const places = useLoreEntries(scenario.lorebook_ids, 'place');
  const people = useLoreEntries(scenario.lorebook_ids, 'person');
  const items = useLoreEntries(scenario.lorebook_ids, 'item');
  if (pending || places.pending) return <p aria-busy="true">불러오는 중</p>;
  const nameOf = placeNameOf(places.entries);
  return (
    <>
      {scenario.lorebook_ids.length === 0 ? (
        <Notice>
          장소는 붙인 로어북의 장소 항목입니다. 로어북을 붙이면 지도를 만들 수 있습니다.{' '}
          <Button variant="quiet" onClick={() => goTo('materials')}>
            재료 탭으로
          </Button>
        </Notice>
      ) : null}
      {places.failed ? <Notice tone="error">로어북의 항목을 불러오지 못했습니다. 장소의 이름이 보이지 않을 수 있습니다.</Notice> : null}
      <StartForm scenario={scenario} places={places.entries} />
      <PlacesSection scenario={scenario} rules={rules} places={places.entries} people={people.entries} items={items.entries} nameOf={nameOf} />
      <RoutesSection scenario={scenario} rules={rules} places={places.entries} items={items.entries} nameOf={nameOf} />
    </>
  );
}

function StartForm({ scenario, places }: { scenario: ScenarioDetail; places: EntryChoice[] }) {
  const [start, setStart] = useState(scenario.start_place ?? '');
  const saving = useScenarioSave(scenario.id);
  const listed = places.some((place) => place.id === start);

  async function submit() {
    const saved = await saving.save({ start_place: start || null });
    if (saved) setStart(saved.start_place ?? '');
  }

  return (
    <ScenarioForm label="지도" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={false} onSubmit={() => void submit()}>
      <SelectField
        label="시작 장소"
        value={start}
        onChange={(event) => setStart(event.target.value)}
        hint="테이블이 시작할 때 모든 캐릭터가 서는 곳입니다. 길이나 명소가 있으면 꼭 있어야 합니다. 비우면 지도가 없는 시나리오입니다."
      >
        <option value="">없음(지도를 쓰지 않음)</option>
        {start !== '' && !listed ? <option value={start}>(붙인 로어북에 없는 장소)</option> : null}
        {places.map((place) => (
          <option key={place.id} value={place.id}>
            {place.name}
          </option>
        ))}
      </SelectField>
    </ScenarioForm>
  );
}
