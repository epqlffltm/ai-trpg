// web/apps/web/src/pages/chat/conversation/shortcutPicks.ts
// 입력칸의 단축어 고르기(#981). 순수한 함수다. chat 의 대화와 story 의 장면이 함께 쓴다.
//
//   - 입력칸이 "/"로 시작하고 아직 이름만 적는 중(빈칸 전)이면 고를 수 있는 목록을 보인다
//   - 적은 만큼으로 시작하는 이름만 보인다. 작품의 것이 먼저다(서버의 차례 그대로)
//   - 고르면 입력칸이 "/이름 "이 된다. 뒤에 하고 싶은 말을 잇는다. 부르는 규칙(맨 앞의 "/이름")은 서버가 본다

import type { ConversationShortcut } from '../../../api/conversationShortcuts';

/** 한 번에 보이는 단축어의 수. 작품 20개와 내 것 20개가 다 보이면 입력칸을 가린다 */
export const PICKS_SHOWN = 8;

/** 적는 중인 이름. 입력칸이 "/"로 시작하고 빈칸이 아직 없을 때만 있다(없으면 null) */
export function typedName(draft: string): string | null {
  const match = /^\/([^\s/]*)$/.exec(draft);
  return match ? (match[1] as string) : null;
}

/** 보일 단축어들. 적은 이름으로 시작하는 것 가운데 앞의 것들이다 */
export function picksFor(draft: string, shortcuts: readonly ConversationShortcut[]): ConversationShortcut[] {
  const typed = typedName(draft);
  if (typed === null) return [];
  return shortcuts.filter((shortcut) => shortcut.name.startsWith(typed)).slice(0, PICKS_SHOWN);
}

/** 고른 단축어를 부르는 입력칸의 글 */
export function pickedDraft(shortcut: ConversationShortcut): string {
  return `/${shortcut.name} `;
}

/** 단추의 글. 설명이 있으면 함께, 내 것이면 표시한다 */
export function pickLabel(shortcut: ConversationShortcut): string {
  const mine = shortcut.source === 'mine' ? ' (내 단축어)' : '';
  const description = shortcut.description.trim() ? ` · ${shortcut.description.trim()}` : '';
  return `/${shortcut.name}${description}${mine}`;
}
