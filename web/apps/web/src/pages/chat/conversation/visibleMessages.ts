// web/apps/web/src/pages/chat/conversation/visibleMessages.ts
// 대사창에 그릴 말들. 답을 받는 동안에는 저장된 말과 흘러 들어오는 글을 맞춘다. 순수한 함수다.
//   - 이어 쓰면: 끊긴 답 뒤에 흘린 글을 붙인다
//   - 말 보내기와 다시 생성: 답할 말까지만 보이고(다시 생성하는 앞의 답은 감춘다), 그 뒤에 흘러 들어오는 답 하나를 둔다
//   - 행동: 행동 말(한마디를 덧붙였으면 행동 말과 한마디)을 끝에 붙이고 반응을 흘린다
//   - 내 말 고치기: 고친 말은 새 가지라 저장된 말에 없다. 고칠 말의 부모까지 보이고 고친 말을 붙인다
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
  if (index >= 0) return { items: saved.slice(0, index + 1), pending: turn.text };
  const added = [turn.action, answering].filter((message): message is SavedChatMessage => message !== null);
  return { items: [...upToParent(saved, added[0] as SavedChatMessage), ...added.map((message) => ({ message: asPathMessage(message), streaming: false }))], pending: turn.text };
}

/** 새 말의 부모까지. 부모가 끝이 아니면(내 말 고치기) 그 뒤를 감춘다. 부모를 모르면 모두 */
function upToParent(saved: VisibleMessage[], first: SavedChatMessage): VisibleMessage[] {
  const parent = saved.findIndex((item) => item.message.id === first.parent_id);
  return parent >= 0 ? saved.slice(0, parent + 1) : saved;
}

/** SSE 의 말(MessageOut)을 대사창의 말 모양으로. 대안은 아직 없다 */
function asPathMessage(message: SavedChatMessage): ConversationMessage {
  return { ...message, alternatives: [message.id] };
}
