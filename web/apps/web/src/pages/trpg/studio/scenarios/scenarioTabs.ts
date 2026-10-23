// web/apps/web/src/pages/trpg/studio/scenarios/scenarioTabs.ts
// 시나리오 고치기(B9)의 탭. 칸의 묶음마다 탭 하나이고, 탭마다 저장한다(그 탭의 칸만 PATCH). 고른 탭은 주소의 ?tab= 에 둔다.
// 게시 점검의 문제는 묶음을 가리킨다(publishProblems.ts). 아직 탭이 없는 묶음도 있다. 화면을 만들면 SCENARIO_TABS 에 더한다.

export type ScenarioTab = 'basics' | 'materials' | 'openings' | 'characters' | 'items' | 'npcs' | 'publish';

/** 칸의 묶음. 탭이 있는 것과 아직 화면이 없는 것(지도, 몬스터, 퀘스트) */
export type ScenarioSection = ScenarioTab | 'map' | 'monsters' | 'quests';

const SECTION_LABELS: Record<ScenarioSection, string> = {
  basics: '기본',
  materials: '재료',
  openings: '스타팅',
  publish: '게시',
  characters: '캐릭터',
  items: '물건·돈',
  npcs: '인물',
  map: '지도',
  monsters: '몬스터',
  quests: '퀘스트',
};

/** 화면의 탭. 차례가 곧 탭의 차례다 */
export const SCENARIO_TABS: ScenarioTab[] = ['basics', 'materials', 'openings', 'characters', 'items', 'npcs', 'publish'];

export function sectionLabel(section: ScenarioSection): string {
  return SECTION_LABELS[section];
}

/** 그 묶음에 탭이 있는가 */
export function isTab(section: ScenarioSection): section is ScenarioTab {
  return (SCENARIO_TABS as string[]).includes(section);
}

/** 주소의 ?tab= 을 탭으로. 모르는 값이나 없으면 기본 */
export function tabOf(value: string | null): ScenarioTab {
  return SCENARIO_TABS.find((tab) => tab === value) ?? 'basics';
}
