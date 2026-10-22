// web/apps/web/src/api/tableRoom.ts
// 테이블 방(B6)이 부르는 것. 테이블 하나, 시작(방장), 나가기, 채팅(읽기, 쓰기, 입력 중), 스트림을 열 번호.
// 앉아 있는 사람만 부른다. 앉지 않았거나 없는 테이블은 404 다(있다는 것을 드러내지 않는다).

import { apiRequest } from './http';
import type { StreamCursor } from './tableStream';
import type { ChatMessage, EventPage, MessagePage, TableDetail, WhisperPage } from './types';

const TABLES = '/api/v1/game/tables';

/** 한 번에 보일 지난 채팅의 수 */
export const CHAT_TAIL = 50;

function tablePath(tableId: string, rest = ''): string {
  return `${TABLES}/${encodeURIComponent(tableId)}${rest}`;
}

export function fetchTable(tableId: string, signal?: AbortSignal): Promise<TableDetail> {
  return apiRequest<TableDetail>(tablePath(tableId), signal ? { signal } : {});
}

/** 테이블을 시작한다(방장). 모두가 캐릭터를 정해야 한다(409 characters_missing) */
export function startTable(tableId: string): Promise<TableDetail> {
  return apiRequest<TableDetail>(tablePath(tableId, '/start'), { method: 'POST' });
}

/** 테이블에서 나간다. 방장이 나가면 가장 먼저 들어온 사람이 방장이 된다 */
export function leaveTable(tableId: string): Promise<void> {
  return apiRequest<void>(tablePath(tableId, '/members/me'), { method: 'DELETE' });
}

/**
 * 지난 채팅의 끝부분(CHAT_TAIL 개). 서버는 번호 차례로 after 뒤를 주고 마지막 번호(last_sequence)를 함께 준다.
 * 마지막 번호를 먼저 묻고(한 줄만), 그 앞의 CHAT_TAIL 개를 읽는다. 번호는 테이블마다 1 부터 빈틈없이 센다
 */
export async function fetchChatTail(tableId: string, signal?: AbortSignal): Promise<MessagePage> {
  const probe = await fetchMessages(tableId, 0, 1, signal);
  const after = Math.max(0, probe.last_sequence - CHAT_TAIL);
  if (after === 0 && probe.last_sequence <= 1) return probe;
  return fetchMessages(tableId, after, CHAT_TAIL, signal);
}

function fetchMessages(tableId: string, after: number, limit: number, signal?: AbortSignal): Promise<MessagePage> {
  return apiRequest<MessagePage>(tablePath(tableId, '/messages'), {
    query: { after, limit },
    ...(signal ? { signal } : {}),
  });
}

/** 채팅을 쓴다(500자까지). 쓴 것은 스트림으로도 다시 온다(번호로 겹친 것을 뺀다) */
export function postMessage(tableId: string, content: string): Promise<ChatMessage> {
  return apiRequest<ChatMessage>(tablePath(tableId, '/messages'), { method: 'POST', body: { content } });
}

/** 입력 중이라고 알린다. 저장하지 않는다. 실패해도 그만이다 */
export function announceTyping(tableId: string): Promise<void> {
  return apiRequest<void>(tablePath(tableId, '/messages/typing'), { method: 'POST' });
}

/**
 * 스트림을 처음 열 번호. 이벤트와 쪽지는 아직 화면에 보이지 않으므로 지금의 마지막 번호부터 받는다.
 * 채팅은 화면이 읽은 끝부분(fetchChatTail)의 마지막 번호다
 */
export async function fetchStreamCursor(tableId: string, messages: number, signal?: AbortSignal): Promise<StreamCursor> {
  const options = { query: { after: 0, limit: 1 }, ...(signal ? { signal } : {}) };
  const [events, whispers] = await Promise.all([
    apiRequest<EventPage>(tablePath(tableId, '/events'), options),
    apiRequest<WhisperPage>(tablePath(tableId, '/whispers'), options),
  ]);
  return { events: events.last_sequence, messages, whispers: whispers.last_sequence };
}
