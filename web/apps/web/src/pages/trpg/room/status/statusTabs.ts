// web/apps/web/src/pages/trpg/room/status/statusTabs.ts
// 왼쪽 열의 창 넷과 단축키(Stitch 20번). 순수한 함수다. C 상태·장비, I 소지품·돈, J 퀘스트·지도, L 일행·기록.
// 창은 하나만 펼친다. 단축키는 그 창을 펼친다(이미 펼쳤으면 그대로).
// 글을 쓰는 칸(입력, 글상자, 고르기)에 있을 때와 Ctrl·Alt·Meta 를 함께 누른 때는 단축키로 보지 않는다.

export type StatusTab = 'mine' | 'items' | 'world' | 'party';

export const STATUS_TABS: { tab: StatusTab; label: string; key: string }[] = [
  { tab: 'mine', label: '상태·장비', key: 'c' },
  { tab: 'items', label: '소지품·돈', key: 'i' },
  { tab: 'world', label: '퀘스트·지도', key: 'j' },
  { tab: 'party', label: '일행·기록', key: 'l' },
];

const TYPING_TAGS: ReadonlySet<string> = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

export type KeyPress = {
  key: string;
  ctrlKey: boolean;
  altKey: boolean;
  metaKey: boolean;
  /** 눌린 곳의 태그 이름(대문자)과 글을 고칠 수 있는 곳인지 */
  targetTag: string;
  targetEditable: boolean;
};

/** 이 키가 펼치는 창. 단축키가 아니면 null */
export function tabForKey(press: KeyPress): StatusTab | null {
  if (press.ctrlKey || press.altKey || press.metaKey) return null;
  if (press.targetEditable || TYPING_TAGS.has(press.targetTag)) return null;
  const key = press.key.toLowerCase();
  return STATUS_TABS.find((entry) => entry.key === key)?.tab ?? null;
}

/** 창 단추를 눌렀을 때 펼쳐 둘 창. 펼친 것을 다시 누르면 모두 접는다(null) */
export function nextOpenTab(current: StatusTab | null, pressed: StatusTab): StatusTab | null {
  return current === pressed ? null : pressed;
}
