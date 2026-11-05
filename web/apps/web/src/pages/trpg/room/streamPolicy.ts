// web/apps/web/src/pages/trpg/room/streamPolicy.ts
// 스트림이 끝난 뒤에 무엇을 할지, 받은 메시지를 어디로 보낼지. 화면을 그리지 않는 순수한 함수다.
//
// 끝난 까닭(trpg-server README 의 "실시간 스트림"):
//   - table_ended: 남은 기록을 다 보낸 뒤 닫았다. 멈추고 테이블을 다시 읽는다(끝난 판의 화면)
//   - not_seated: 나갔거나 내보내졌다. 멈춘다
//   - token_expired, 401: 토큰을 갱신하고 바로 다시 붙는다. 갱신도 안 되면 로그인이 끝났다
//   - server_shutdown, 끊김: 1~5초 사이에서 무작위로 쉬었다가 다시 붙는다(모두가 한꺼번에 붙지 않게)
//   - 그 밖의 HTTP 오류: 404 는 앉아 있지 않은 것이다. 나머지는 쉬는 시간을 늘려 가며 다시 붙는다(30초까지)

import type { SseMessage } from '../../../api/sse';
import type { StreamEnd } from '../../../api/tableStream';
import type { ChatMessage, TableEvent, Whisper } from '../../../api/types';

/** aborted: 화면을 떠나 쓰는 쪽이 끊었다 */
export type StopReason = 'table_ended' | 'not_seated' | 'signed_out' | 'aborted';

export type NextStep =
  | { action: 'reconnect'; delayMs: number }
  | { action: 'refresh-token' }
  | { action: 'stop'; reason: StopReason };

const JITTER_MIN_MS = 1000;
const JITTER_MAX_MS = 5000;
const BACKOFF_MAX_MS = 30_000;

/** failures: 열리지 못하고 이어서 실패한 수(열리면 0 으로 돌린다). random: 0 이상 1 미만 */
export function nextStep(end: StreamEnd, failures: number, random: number): NextStep {
  switch (end.kind) {
    case 'closed':
      return afterClosed(end.reason, random);
    case 'unauthorized':
      return { action: 'refresh-token' };
    case 'http-error':
      if (end.status === 404) return { action: 'stop', reason: 'not_seated' };
      return { action: 'reconnect', delayMs: backoff(failures, random) };
    case 'disconnected':
      return { action: 'reconnect', delayMs: jitter(random) };
    case 'aborted':
      return { action: 'stop', reason: 'aborted' };
  }
}

function afterClosed(reason: string, random: number): NextStep {
  if (reason === 'table_ended') return { action: 'stop', reason: 'table_ended' };
  if (reason === 'not_seated') return { action: 'stop', reason: 'not_seated' };
  if (reason === 'token_expired') return { action: 'refresh-token' };
  return { action: 'reconnect', delayMs: jitter(random) };
}

function jitter(random: number): number {
  return Math.round(JITTER_MIN_MS + random * (JITTER_MAX_MS - JITTER_MIN_MS));
}

/** 이어서 실패할수록 길게: 1~5초, 2~10초, 4~20초 … 30초까지 */
function backoff(failures: number, random: number): number {
  return Math.min(BACKOFF_MAX_MS, jitter(random) * 2 ** Math.max(0, failures - 1));
}

/** 쓰이는 중인 서술의 조각(narration_preview). id 가 없어 다시 붙으면 다시 오지 않는다 */
export type PreviewChunk = { round: number; attempt: number; seq: number; text: string };

/** 받은 메시지의 갈래. 모르는 것(쪽지는 아직 쓰지 않는다)은 ignore 다 */
export type Routed =
  | { kind: 'event'; event: TableEvent }
  | { kind: 'chat'; message: ChatMessage }
  | { kind: 'whisper'; whisper: Whisper }
  | { kind: 'typing'; userId: string }
  | { kind: 'preview'; chunk: PreviewChunk }
  | { kind: 'snapshot' }
  | { kind: 'ignore' };

export function routeMessage(message: SseMessage): Routed {
  const data = parseObject(message.data);
  if (!data) return { kind: 'ignore' };
  switch (message.event) {
    case 'table_event':
      return { kind: 'event', event: data as TableEvent };
    case 'chat_message':
      return { kind: 'chat', message: data as ChatMessage };
    case 'whisper':
      // 내 쪽지함에 적힌 쪽지(보낸 것과 받은 것). 번호는 쪽지함마다 센다
      return { kind: 'whisper', whisper: data as Whisper };
    case 'typing':
      return typeof data.user_id === 'string' ? { kind: 'typing', userId: data.user_id } : { kind: 'ignore' };
    case 'narration_preview':
      return toPreview(data);
    case 'scene_snapshot':
      // 장면 그림이 바뀌었다(#983). 내용이 없다. 받은 쪽이 목록을 다시 읽는다
      return { kind: 'snapshot' };
    default:
      return { kind: 'ignore' };
  }
}

function toPreview(data: Record<string, unknown>): Routed {
  const { round, attempt, seq, text } = data;
  if (typeof round !== 'number' || typeof attempt !== 'number' || typeof seq !== 'number' || typeof text !== 'string') {
    return { kind: 'ignore' };
  }
  return { kind: 'preview', chunk: { round, attempt, seq, text } };
}

function parseObject(text: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(text);
    return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** 채팅을 번호 차례로 합친다. 같은 번호는 한 번만(쓴 사람이 받은 응답과 스트림이 같은 것을 준다) */
export function mergeMessages(current: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const bySequence = new Map(current.map((message) => [message.sequence, message]));
  for (const message of incoming) bySequence.set(message.sequence, message);
  return [...bySequence.values()].sort((a, b) => a.sequence - b.sequence);
}

/** 일어난 일을 번호 차례로 합친다. 같은 번호는 한 번만(다시 붙을 때 겹칠 수 있다) */
export function mergeEvents(current: TableEvent[], incoming: TableEvent[]): TableEvent[] {
  const bySequence = new Map(current.map((event) => [event.sequence, event]));
  for (const event of incoming) bySequence.set(event.sequence, event);
  return [...bySequence.values()].sort((a, b) => a.sequence - b.sequence);
}

/** 쪽지를 번호 차례로 합친다. 같은 번호는 한 번만(보낸 사람이 받은 응답과 스트림이 같은 것을 준다) */
export function mergeWhispers(current: Whisper[], incoming: Whisper[]): Whisper[] {
  const bySequence = new Map(current.map((whisper) => [whisper.sequence, whisper]));
  for (const whisper of incoming) bySequence.set(whisper.sequence, whisper);
  return [...bySequence.values()].sort((a, b) => a.sequence - b.sequence);
}

/**
 * 쪽지 탭의 안 읽은 수. 쪽지 탭을 보고 있지 않을 때 스트림으로 나에게 온 쪽지만 센다.
 * 서버는 읽음을 적지 않는다. 그래서 방에 들어오기 전에 온 쪽지는 세지 않는다(이 화면을 연 동안만 센다)
 */
export function nextUnreadWhispers(current: number, whisper: Whisper, myId: string | undefined, viewing: boolean): number {
  if (viewing || myId === undefined || whisper.recipient_id !== myId || whisper.sender_id === myId) return current;
  return current + 1;
}
