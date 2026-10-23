// web/apps/web/src/pages/trpg/studio/scenarios/QuestsTab.tsx
// 시나리오의 퀘스트·사건 탭(B9). 탭의 저장은 없고 모두 창에서 바로 저장한다: 퀘스트(QuestsSection)와 사건(HappeningsSection).
// 조건과 효과가 가리키는 것: 장소·물건·인물·사건은 저장된 로어북들의 항목, 몬스터는 시트를 적은 몬스터다.

import { Button, Notice } from '@ai-trpg/ui';
import type { ScenarioDetail } from '../../../../api/types';
import type { Targets } from './conditionsForm';
import { HappeningsSection } from './HappeningsSection';
import { QuestsSection } from './QuestsSection';
import type { ScenarioTab } from './scenarioTabs';
import { monsterNameOf, useBestiaryMonsters } from './useBestiaryMonsters';
import { useLoreEntries } from './useLoreEntries';
import { useScenarioRules } from './useScenarioRules';

type Props = { scenario: ScenarioDetail; goTo: (tab: ScenarioTab) => void };

export function QuestsTab({ scenario, goTo }: Props) {
  const { rules, pending } = useScenarioRules(scenario);
  const events = useLoreEntries(scenario.lorebook_ids, 'event');
  const places = useLoreEntries(scenario.lorebook_ids, 'place');
  const items = useLoreEntries(scenario.lorebook_ids, 'item');
  const npcs = useLoreEntries(scenario.lorebook_ids, 'person');
  const monsters = useBestiaryMonsters(scenario.bestiary_ids);
  if (pending || events.pending || monsters.pending) return <p aria-busy="true">불러오는 중</p>;
  const monsterName = monsterNameOf(monsters.monsters);
  const targets: Targets = {
    places: places.entries,
    items: items.entries,
    npcs: npcs.entries,
    quests: events.entries,
    monsters: scenario.monster_sheets.map((sheet) => ({ id: sheet.monster_id, name: monsterName(sheet.monster_id) })),
  };
  return (
    <>
      {scenario.lorebook_ids.length === 0 ? (
        <Notice>
          퀘스트와 사건은 붙인 로어북의 사건 항목입니다. 로어북을 붙이면 정할 수 있습니다.{' '}
          <Button variant="quiet" onClick={() => goTo('materials')}>
            재료 탭으로
          </Button>
        </Notice>
      ) : null}
      {events.failed ? <Notice tone="error">로어북의 항목을 불러오지 못했습니다. 이름이 보이지 않을 수 있습니다.</Notice> : null}
      <QuestsSection scenario={scenario} rules={rules} targets={targets} />
      <HappeningsSection scenario={scenario} targets={targets} />
    </>
  );
}
