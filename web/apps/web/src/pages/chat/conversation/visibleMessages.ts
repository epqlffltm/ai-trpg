// web/apps/web/src/pages/chat/conversation/visibleMessages.ts
// 대사창에 그릴 말들. 답을 받는 동안에는 저장된 말과 흘러 들어오는 글을 맞춘다. 순수한 함수다.
//   - 이어 쓰면: 끊긴 답 뒤에 흘린 글을 붙인다
//   - 말 보내기와 다시 생성: 답할 말까지만 보이고(다시 생성하는 앞의 답은 감춘다), 그 뒤에 흘러 들어오는 답 하나를 둔다
//   - turn 을 받기 전이면 저장된 말 그대로다

import type { ConversationMessage, SavedChatMessage } from '../../../api/types';
import type { TurnState } from './turnState';

export type VisibleMessage = { message: ConversationMessage; streaming: boolean };

export function visibleMessages(messages: ConversationMessage[], turn: TurnState | null): { items: VisibleMessage[]; pending: string | null } {
  const saved = messages.map((message) => ({ message, streaming: false }));
  if (!turn?.userMessage) return { items: saved, pending: null };
  if (turn.continues) {
    return {
      items: saved.map((item) => (item.message.id === turn.continues ? { message: { ...item.message, content: item.message.content + turn.text }, streaming: true } : item)),
      pending: null,
    };
  }
  const answering = turn.userMessage;
  const index = messages.findIndex((message) => message.id === answering.id);
  const before = index >= 0 ? saved.slice(0, index + 1) : [...saved, { message: asPathMessage(answering), streaming: false }];
  return { items: before, pending: turn.text };
}

/** SSE 의 말(MessageOut)을 대사창의 말 모양으로. 대안은 아직 없다 */
function asPathMessage(message: SavedChatMessage): ConversationMessage {
  return { ...message, alternatives: [message.id] };
}
