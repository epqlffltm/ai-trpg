// web/apps/web/src/api/conversationShortcuts.ts
// 대화에서 고를 수 있는 단축어(#981). chat 의 대화와 story 의 세션이 같은 모양이다.
//   - 작품(캐릭터, 세계관)의 것이 먼저, 그 뒤에 내 단축어다. 같은 이름의 내 것은 빠져 있다
//   - 본문은 싣지 않는다. 부르는 것은 말을 "/이름"으로 시작해 보내는 것이다(서버가 찾아 붙인다)
//   - asset 서버를 쓸 수 없으면 작품의 것만 온다. 남의 대화는 404

import type { components as Chat } from './generated/chat';
import type { components as Story } from './generated/story';
import { apiRequest } from './http';

export type ShortcutService = 'chat' | 'story';
export type ConversationShortcut = Chat['schemas']['ShortcutOut'] | Story['schemas']['ShortcutOut'];

export function fetchConversationShortcuts(service: ShortcutService, conversationId: string, signal?: AbortSignal): Promise<ConversationShortcut[]> {
  const path = `/api/v1/${service}/conversations/${encodeURIComponent(conversationId)}/shortcuts`;
  return apiRequest<ConversationShortcut[]>(path, signal ? { signal } : {});
}
