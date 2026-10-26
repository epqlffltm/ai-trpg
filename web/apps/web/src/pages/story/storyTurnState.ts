// web/apps/web/src/pages/story/storyTurnState.ts
// 답을 받는 동안의 화면 상태. SSE 메시지를 하나씩 넣어 다음 상태를 만든다. 순수한 함수다.
//
//   turn     → 답할 말(사람의 말이나 행동 말), 멈출 때 쓰는 generation_id, 장면의 인물(cast), 그 뒤의 상태(state)
//   segment  → 새 말 조각. 뒤의 delta 는 이 사람의 것이다(서술은 speaker 가 null)
//   delta    → 지금 조각에 글을 잇는다
//   done     → 저장한 답. 끝
//   failed   → 글자 없이 실패. 끝
// 모양이 틀린 메시지는 버린다. 끝나면 세션을 다시 읽는다(흘린 글과 저장한 답이 어긋나면 저장한 것을 믿는다).

import type { SseMessage } from '../../api/sse';
import type { StorySavedMessage, StorySegment, StoryState } from '../../api/story';

export type StoryTurnState = {
  generationId: string | null;
  userMessage: StorySavedMessage | null;
  cast: string[];
  state: StoryState | null;
  segments: StorySegment[];
  end: { kind: 'done'; message: StorySavedMessage } | { kind: 'failed'; code: string } | null;
};

export const EMPTY_STORY_TURN: StoryTurnState = { generationId: null, userMessage: null, cast: [], state: null, segments: [], end: null };

export function applyStoryTurnMessage(turn: StoryTurnState, message: SseMessage): StoryTurnState {
  const data = parseObject(message.data);
  if (!data || turn.end) return turn;
  if (message.event === 'turn') return applyStart(turn, data);
  if (message.event === 'segment') return { ...turn, segments: [...turn.segments, { speaker: typeof data.speaker === 'string' ? data.speaker : null, text: '' }] };
  if (message.event === 'delta' && typeof data.text === 'string') return applyDelta(turn, data.text);
  if (message.event === 'done' && isMessage(data.message)) return { ...turn, end: { kind: 'done', message: data.message } };
  if (message.event === 'failed') return { ...turn, end: { kind: 'failed', code: typeof data.code === 'string' ? data.code : 'unknown' } };
  return turn;
}

function applyStart(turn: StoryTurnState, data: Record<string, unknown>): StoryTurnState {
  return {
    ...turn,
    generationId: typeof data.generation_id === 'string' ? data.generation_id : null,
    userMessage: isMessage(data.user_message) ? data.user_message : null,
    cast: Array.isArray(data.cast) ? data.cast.filter((id): id is string => typeof id === 'string') : [],
    state: isState(data.state) ? data.state : null,
  };
}

/** 지금 조각에 잇는다. segment 보다 먼저 온 글은 서술의 조각으로 연다 */
function applyDelta(turn: StoryTurnState, text: string): StoryTurnState {
  const last = turn.segments.at(-1);
  if (!last) return { ...turn, segments: [{ speaker: null, text }] };
  return { ...turn, segments: [...turn.segments.slice(0, -1), { ...last, text: last.text + text }] };
}

function parseObject(text: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(text);
    return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function isMessage(value: unknown): value is StorySavedMessage {
  const candidate = value as Partial<StorySavedMessage> | null;
  return candidate !== null && typeof candidate === 'object' && typeof candidate.id === 'string' && typeof candidate.role === 'string' && Array.isArray(candidate.segments);
}

function isState(value: unknown): value is StoryState {
  const candidate = value as Partial<StoryState> | null;
  return candidate !== null && typeof candidate === 'object' && typeof candidate.day === 'number' && typeof candidate.slot === 'string' && typeof candidate.place === 'string';
}
