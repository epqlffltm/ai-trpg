// web/apps/web/src/pages/story/storyView.ts
// 대사창에 그릴 말과 끝에서 할 수 있는 일. 순수한 함수다.
//   - 답을 받는 동안: 답할 말까지 보이고(다시 생성하는 앞의 답은 감춘다), 그 뒤에 흘러 들어오는 조각들을 둔다
//   - 답할 말이 저장된 말에 없으면(방금 보낸 말) 끝에 붙인다
//   - 장면의 인물과 상태는 받는 중이면 turn 의 것, 아니면 세션의 것이다

import type { StoryMessage, StorySavedMessage, StorySegment, StoryState } from '../../api/story';
import type { StoryTurnState } from './storyTurnState';

export type StoryVisible = { items: StoryMessage[]; pending: StorySegment[] | null };

export function visibleStoryMessages(messages: StoryMessage[], turn: StoryTurnState | null): StoryVisible {
  if (!turn?.userMessage) return { items: messages, pending: null };
  const answering = turn.userMessage;
  const index = messages.findIndex((message) => message.id === answering.id);
  if (index >= 0) return { items: messages.slice(0, index + 1), pending: turn.segments };
  return { items: [...messages, asPathMessage(answering)], pending: turn.segments };
}

function asPathMessage(message: StorySavedMessage): StoryMessage {
  return { ...message, alternatives: [message.id] };
}

/** 끝에서 할 수 있는 일. 끝이 답을 못 받은 사람의 말이나 행동 말이면 답 받기, 답이면 다시 생성(부모가 없는 답은 빼고) */
export function storyTail(messages: StoryMessage[]): { answer: string | null; regenerate: string | null } {
  const last = messages.at(-1);
  if (!last) return { answer: null, regenerate: null };
  if (last.role !== 'assistant') return { answer: last.id, regenerate: null };
  return { answer: null, regenerate: last.parent_id === null ? null : last.id };
}

/** 지금 보일 장면의 인물과 상태. 받는 중이면 turn 이 알린 것이다 */
export function sceneOf(state: StoryState, turn: StoryTurnState | null): { state: StoryState; cast: string[] } {
  const current = turn?.state ?? state;
  return { state: current, cast: turn?.state ? turn.cast : current.cast };
}

/** 대안 사이의 자리. 대안이 하나면 null */
export function storyAlternatives(message: Pick<StoryMessage, 'id' | 'alternatives'>): { position: number; count: number; previous: string | null; next: string | null } | null {
  const ids = message.alternatives;
  const index = ids.indexOf(message.id);
  if (ids.length < 2 || index < 0) return null;
  return { position: index + 1, count: ids.length, previous: ids[index - 1] ?? null, next: ids[index + 1] ?? null };
}
