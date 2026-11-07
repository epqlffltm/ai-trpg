// web/apps/web/src/pages/me/myTabs.ts
// 마이페이지(Stitch 10번)의 탭 넷과 주소의 ?tab= 을 읽는 것. 순수한 값과 함수다.

export type MyTab = 'account' | 'points' | 'settings' | 'creator';

/** 탭의 차례. 설계서의 "내 계정", "내 포인트", "설정", "제작자" */
export const MY_TABS: { value: MyTab; label: string }[] = [
  { value: 'account', label: '내 계정' },
  { value: 'points', label: '내 포인트' },
  { value: 'settings', label: '설정' },
  { value: 'creator', label: '제작자' },
];

/** 주소의 ?tab= 을 탭으로. 없거나 모르는 값이면 내 계정 */
export function myTabOf(value: string | null): MyTab {
  return MY_TABS.find((tab) => tab.value === value)?.value ?? 'account';
}

/** 그 탭을 연 마이페이지의 주소 */
export function myTabPath(tab: MyTab): string {
  return tab === 'account' ? '/me' : `/me?tab=${tab}`;
}
