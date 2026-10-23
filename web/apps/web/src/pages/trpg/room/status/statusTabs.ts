// web/apps/web/src/pages/trpg/room/status/statusTabs.ts
// 상태 패널의 탭과 단축키. 순수한 함수다. C 캐릭터, I 소지품, J 퀘스트와 장소, L 일어난 일.
// 명세(B7)는 J 에 퀘스트와 기록을 함께 두었다. 기록이 길어 L 로 나눴다(docs/product/screens.md 의 ④-2).
// 글을 쓰는 칸(입력, 글상자, 고르기)에 있을 때와 Ctrl·Alt·Meta 를 함께 누른 때는 단축키로 보지 않는다.

export type StatusTab = 'characters' | 'items' | 'world' | 'log';

export const STATUS_TABS: { tab: StatusTab; label: string; key: string }[] = [
  { tab: 'characters', label: '캐릭터', key: 'c' },
  { tab: 'items', label: '소지품', key: 'i' },
  { tab: 'world', label: '퀘스트·장소', key: 'j' },
  { tab: 'log', label: '일어난 일', key: 'l' },
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

/** 이 키가 고르는 탭. 단축키가 아니면 null */
export function tabForKey(press: KeyPress): StatusTab | null {
  if (press.ctrlKey || press.altKey || press.metaKey) return null;
  if (press.targetEditable || TYPING_TAGS.has(press.targetTag)) return null;
  const key = press.key.toLowerCase();
  return STATUS_TABS.find((entry) => entry.key === key)?.tab ?? null;
}
