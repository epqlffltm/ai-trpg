// web/apps/web/src/pages/chat/conversation/turnState.ts
// 답을 받는 동안의 화면 상태. SSE 메시지를 하나씩 넣어 다음 상태를 만든다. 순수한 함수다.
//
//   turn        → 답할 사람의 말(user_message), 멈출 때 쓰는 generation_id, 이어 쓰면 그 말의 id(continues)
//   expression  → 지금 띄울 캐릭터 그림(sprite). 첫 delta 보다 먼저 온다
//   delta       → 흘러 들어온 글을 잇는다
//   done        → 저장한 답. 끝
//   failed      → 글자 없이 실패. 끝(code 는 timeout, status_429, empty, stopped …)
// 모양이 틀린 메시지는 버린다. 끝난 뒤의 대화는 서버에서 다시 읽는다(흘린 글과 저장한 답이 어긋나면 저장한 것을 믿는다).

import type { SseMessage } from '../../../api/sse';
import type { SavedChatMessage } from '../../../api/types';

export type TurnState = {
  /** 멈추기에 쓴다. turn 을 받기 전이면 null */
  generationId: string | null;
  /** 답할 사람의 말. 말 보내기면 방금 보낸 말이다 */
  userMessage: SavedChatMessage | null;
  /** 이어 쓰는 끊긴 답의 id. 아니면 null */
  continues: string | null;
  /** 흘러 들어온 글. 이어 쓰면 끊긴 답 뒤에 붙일 글이다 */
  text: string;
  sprite: string | null;
  /** 끝났으면 저장한 답(done) 이나 실패의 까닭(failed) */
  end: { kind: 'done'; message: SavedChatMessage } | { kind: 'failed'; code: string } | null;
};

export const EMPTY_TURN: TurnState = { generationId: null, userMessage: null, continues: null, text: '', sprite: null, end: null };

export function applyTurnMessage(state: TurnState, message: SseMessage): TurnState {
  const data = parseObject(message.data);
  if (!data || state.end) return state;
  if (message.event === 'turn') return applyTurnStart(state, data);
  if (message.event === 'expression' && typeof data.sprite === 'string') return { ...state, sprite: data.sprite };
  if (message.event === 'delta' && typeof data.text === 'string') return { ...state, text: state.text + data.text };
  if (message.event === 'done' && isMessage(data.message)) return { ...state, end: { kind: 'done', message: data.message } };
  if (message.event === 'failed') return { ...state, end: { kind: 'failed', code: typeof data.code === 'string' ? data.code : 'unknown' } };
  return state;
}

function applyTurnStart(state: TurnState, data: Record<string, unknown>): TurnState {
  return {
    ...state,
    generationId: typeof data.generation_id === 'string' ? data.generation_id : null,
    userMessage: isMessage(data.user_message) ? data.user_message : null,
    continues: typeof data.continues === 'string' ? data.continues : null,
  };
}

function parseObject(text: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(text);
    return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function isMessage(value: unknown): value is SavedChatMessage {
  const candidate = value as Partial<SavedChatMessage> | null;
  return candidate !== null && typeof candidate === 'object' && typeof candidate.id === 'string' && typeof candidate.content === 'string' && typeof candidate.role === 'string';
}

/** 실패의 까닭을 한 줄로. 글자 없이 실패했으면 청구하지 않았다 */
export function failedText(code: string): string {
  if (code === 'stopped') return '멈췄습니다. 받은 글이 없어 청구하지 않았습니다.';
  const reason: Record<string, string> = {
    timeout: '모델이 제때 답하지 않았습니다',
    status_429: '모델을 부르는 곳이 지금 붐빕니다',
    empty: '모델이 빈 답을 냈습니다',
    cancelled: '서버가 다시 시작되며 멈췄습니다',
  };
  return `${reason[code] ?? '답을 받지 못했습니다'}. 청구하지 않았습니다. 다시 생성해 보세요.`;
}
