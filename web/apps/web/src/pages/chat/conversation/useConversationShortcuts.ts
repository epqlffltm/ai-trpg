// web/apps/web/src/pages/chat/conversation/useConversationShortcuts.ts
// 대화에서 고를 수 있는 단축어(#981)를 읽는다. 입력칸이 "/"로 시작할 때 처음 읽는다(보통의 말에는 부르지 않는다).
// 한 번 읽으면 잠시 그대로 쓴다. 읽지 못하면 목록 없이 둔다(부르는 것은 서버가 하므로 "/이름"을 적어 보내면 된다).

import { queryOptions, useQuery } from '@tanstack/react-query';
import { fetchConversationShortcuts, type ConversationShortcut, type ShortcutService } from '../../../api/conversationShortcuts';
import { typedName } from './shortcutPicks';

/** 읽은 목록을 다시 읽지 않고 쓰는 시간. 내 단축어를 다른 탭에서 고쳤으면 그 뒤에 보인다 */
const FRESH_MS = 60_000;

export function conversationShortcutsQuery(service: ShortcutService, conversationId: string) {
  return queryOptions({
    queryKey: [service, 'conversation', conversationId, 'shortcuts'] as const,
    queryFn: ({ signal }) => fetchConversationShortcuts(service, conversationId, signal),
    staleTime: FRESH_MS,
    retry: false,
  });
}

export function useConversationShortcuts(service: ShortcutService, conversationId: string, draft: string): ConversationShortcut[] {
  const asked = typedName(draft) !== null;
  const shortcuts = useQuery({ ...conversationShortcutsQuery(service, conversationId), enabled: asked });
  return shortcuts.data ?? [];
}
