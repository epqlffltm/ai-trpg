// web/apps/web/src/pages/trpg/studio/scenarios/MonstersTab.tsx
// 시나리오의 몬스터 탭(B9). 탭의 저장은 없고 모두 창에서 바로 저장한다: 몬스터 시트(MonsterSheetsSection), 조우(EncountersSection),
// 무작위 조우 표(WandersSection, #283).
// 몬스터는 저장된 몬스터 모음들의 몬스터, 지닌 물건은 로어북의 물건 항목, 조우의 장소는 로어북의 장소 항목이다.

import { Button, Notice } from '@ai-trpg/ui';
import type { ScenarioDetail } from '../../../../api/types';
import { EncountersSection } from './EncountersSection';
import { MonsterSheetsSection } from './MonsterSheetsSection';
import { placeNameOf } from './placesForm';
import type { ScenarioTab } from './scenarioTabs';
import { monsterNameOf, useBestiaryMonsters } from './useBestiaryMonsters';
import { useLoreEntries } from './useLoreEntries';
import { useScenarioRules } from './useScenarioRules';
import { WandersSection } from './WandersSection';

type Props = { scenario: ScenarioDetail; goTo: (tab: ScenarioTab) => void };

export function MonstersTab({ scenario, goTo }: Props) {
  const { rules, pending } = useScenarioRules(scenario);
  const monsters = useBestiaryMonsters(scenario.bestiary_ids);
  const places = useLoreEntries(scenario.lorebook_ids, 'place');
  const items = useLoreEntries(scenario.lorebook_ids, 'item');
  if (pending || monsters.pending) return <p aria-busy="true">불러오는 중</p>;
  return (
    <>
      {scenario.bestiary_ids.length === 0 || !rules ? (
        <Notice>
          몬스터는 붙인 몬스터 모음의 몬스터이고, 숫자는 룰북이 정합니다. 몬스터 모음과 룰북을 고르면 시트를 적을 수 있습니다.{' '}
          <Button variant="quiet" onClick={() => goTo('materials')}>
            재료 탭으로
          </Button>
        </Notice>
      ) : null}
      {monsters.failed ? <Notice tone="error">몬스터 모음을 불러오지 못했습니다. 몬스터의 이름이 보이지 않을 수 있습니다.</Notice> : null}
      <MonsterSheetsSection scenario={scenario} rules={rules} monsters={monsters.monsters} items={items.entries} />
      <EncountersSection
        scenario={scenario}
        places={places.entries}
        monsters={monsters.monsters}
        placeName={placeNameOf(places.entries)}
        monsterName={monsterNameOf(monsters.monsters)}
      />
      <WandersSection scenario={scenario} places={places.entries} placeName={placeNameOf(places.entries)} monsterName={monsterNameOf(monsters.monsters)} />
    </>
  );
}
