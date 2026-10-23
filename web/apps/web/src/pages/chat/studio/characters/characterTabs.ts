// web/apps/web/src/pages/chat/studio/characters/characterTabs.ts
// 캐릭터 고치기(C6)의 탭. 칸의 묶음마다 탭 하나이고, 탭마다 저장한다(그 탭의 칸만 PATCH). 고른 탭은 주소의 ?tab= 에 둔다.
// 게시 점검의 문제는 그 칸이 있는 탭을 가리킨다(publishProblems.ts).

export type CharacterTab =
  | 'basics'
  | 'intro'
  | 'speech'
  | 'starts'
  | 'map'
  | 'items'
  | 'affection'
  | 'images'
  | 'sprites'
  | 'scenes'
  | 'lorebooks'
  | 'publish';

const TAB_LABELS: Record<CharacterTab, string> = {
  basics: '기본',
  intro: '소개',
  speech: '말',
  starts: '시작 상황',
  publish: '게시',
  map: '지도',
  items: '물건',
  affection: '호감도',
  images: '그림',
  sprites: '캐릭터 그림',
  scenes: '이벤트 씬',
  lorebooks: '로어북',
};

/** 화면의 탭. 차례가 곧 탭의 차례다 */
export const CHARACTER_TABS: CharacterTab[] = [
  'basics',
  'intro',
  'speech',
  'starts',
  'map',
  'items',
  'affection',
  'images',
  'sprites',
  'scenes',
  'lorebooks',
  'publish',
];

export function tabLabel(tab: CharacterTab): string {
  return TAB_LABELS[tab];
}

/** 주소의 ?tab= 을 탭으로. 모르는 값이나 없으면 기본 */
export function tabOf(value: string | null): CharacterTab {
  return CHARACTER_TABS.find((tab) => tab === value) ?? 'basics';
}
