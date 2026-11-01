// web/apps/web/src/pages/trpg/studio/scenarios/useConditionTargets.ts
// 조건과 효과가 고를 대상들(B9). 퀘스트·사건 탭과 장 탭이 함께 쓴다.
// 장소·물건·인물·사건은 저장된 로어북들의 항목, 몬스터는 시트를 적은 몬스터, 장은 저장된 시나리오의 장(#481)이다.

import type { ScenarioDetail } from '../../../../api/types';
import type { Targets } from './conditionsForm';
import { monsterNameOf, useBestiaryMonsters } from './useBestiaryMonsters';
import { useLoreEntries } from './useLoreEntries';

export function useConditionTargets(scenario: ScenarioDetail) {
  const events = useLoreEntries(scenario.lorebook_ids, 'event');
  const places = useLoreEntries(scenario.lorebook_ids, 'place');
  const items = useLoreEntries(scenario.lorebook_ids, 'item');
  const npcs = useLoreEntries(scenario.lorebook_ids, 'person');
  const monsters = useBestiaryMonsters(scenario.bestiary_ids);
  const monsterName = monsterNameOf(monsters.monsters);
  const targets: Targets = {
    places: places.entries,
    items: items.entries,
    npcs: npcs.entries,
    quests: events.entries,
    monsters: scenario.monster_sheets.map((sheet) => ({ id: sheet.monster_id, name: monsterName(sheet.monster_id) })),
    chapters: scenario.chapters.map((chapter) => ({ id: chapter.id, name: chapter.name })),
  };
  return { targets, pending: events.pending || monsters.pending, failed: events.failed };
}
