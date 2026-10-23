// web/apps/web/src/pages/chat/studio/characters/characterTabs.ts
// 캐릭터 고치기(C6)의 탭. 칸의 묶음마다 탭 하나이고, 탭마다 저장한다(그 탭의 칸만 PATCH). 고른 탭은 주소의 ?tab= 에 둔다.
// 게시 점검의 문제는 묶음을 가리킨다(publishProblems.ts). 아직 탭이 없는 묶음도 있다(호감도, 그림, 로어북).
// 화면을 만들면 CHARACTER_TABS 에 더한다(#673).

export type CharacterTab = 'basics' | 'intro' | 'speech' | 'starts' | 'map' | 'items' | 'publish';

/** 칸의 묶음. 탭이 있는 것과 아직 화면이 없는 것 */
export type CharacterSection = CharacterTab | 'affection' | 'images' | 'lorebooks';

const SECTION_LABELS: Record<CharacterSection, string> = {
  basics: '기본',
  intro: '소개',
  speech: '말',
  starts: '시작 상황',
  publish: '게시',
  map: '지도',
  items: '물건',
  affection: '호감도',
  images: '그림',
  lorebooks: '로어북',
};

/** 화면의 탭. 차례가 곧 탭의 차례다 */
export const CHARACTER_TABS: CharacterTab[] = ['basics', 'intro', 'speech', 'starts', 'map', 'items', 'publish'];

export function sectionLabel(section: CharacterSection): string {
  return SECTION_LABELS[section];
}

/** 그 묶음에 탭이 있는가 */
export function isTab(section: CharacterSection): section is CharacterTab {
  return (CHARACTER_TABS as string[]).includes(section);
}

/** 주소의 ?tab= 을 탭으로. 모르는 값이나 없으면 기본 */
export function tabOf(value: string | null): CharacterTab {
  return CHARACTER_TABS.find((tab) => tab === value) ?? 'basics';
}
