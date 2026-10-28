// web/apps/web/src/pages/story/studio/worldTabs.ts
// 세계관 고치기(D7)의 탭. 칸의 묶음마다 탭 하나이고 탭마다 저장한다(그 탭의 칸만 PATCH). 고른 탭은 주소의 ?tab= 에 둔다.
// 탭은 그 칸만 보내므로 다른 탭의 칸은 저장된 그대로 남는다.

export type WorldTab = 'basics' | 'intro' | 'progress' | 'map' | 'items' | 'cast' | 'events' | 'endings' | 'lorebooks' | 'publish';

const TAB_LABELS: Record<WorldTab, string> = {
  basics: '기본',
  intro: '소개',
  progress: '진행',
  map: '지도',
  items: '물건',
  cast: '인물',
  events: '이벤트',
  endings: '엔딩',
  lorebooks: '로어북',
  publish: '게시',
};

/** 화면의 탭. 차례가 곧 탭의 차례다 */
export const WORLD_TABS: WorldTab[] = ['basics', 'intro', 'progress', 'map', 'items', 'cast', 'events', 'endings', 'lorebooks', 'publish'];

export function worldTabLabel(tab: WorldTab): string {
  return TAB_LABELS[tab];
}

/** 주소의 ?tab= 을 탭으로. 모르는 값이나 없으면 기본 */
export function worldTabOf(value: string | null): WorldTab {
  return WORLD_TABS.find((tab) => tab === value) ?? 'basics';
}
