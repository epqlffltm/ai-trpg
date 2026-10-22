// web/apps/web/src/api/tableStream.ts
// 테이블의 스트림(GET /tables/{id}/stream, SSE)을 한 번 열고 끝날 때까지 읽는다. 다시 붙는 것은 쓰는 쪽(useTableStream)이 정한다.
//
// EventSource 는 Authorization 머리말을 붙이지 못해 fetch 로 읽는다(trpg-server README 의 "실시간 스트림").
// 처음에는 REST 로 읽은 마지막 번호(events_after, messages_after, whispers_after)로 붙고, 끊겼다 다시 붙을 때는
// 마지막으로 받은 메시지의 id 를 Last-Event-ID 로 보낸다. 서버는 그 뒤의 것부터 보낸다.
// 이 함수는 401 에서 토큰을 갱신하지 않는다. 끝난 까닭(unauthorized)만 돌려준다. 갱신은 한 번에 하나라 쓰는 쪽이 refresh.ts 로 한다.

import { getSession } from './session';
import { splitSse, type SseMessage } from './sse';

export type StreamCursor = { events: number; messages: number; whispers: number };

/** 스트림이 끝난 까닭 */
export type StreamEnd =
  | { kind: 'closed'; reason: string }
  | { kind: 'unauthorized' }
  | { kind: 'http-error'; status: number }
  | { kind: 'disconnected' }
  | { kind: 'aborted' };

export type StreamOptions = {
  tableId: string;
  cursor: StreamCursor;
  /** 마지막으로 받은 메시지의 id. 있으면 cursor 대신 이것으로 이어 받는다 */
  lastEventId: string | null;
  signal: AbortSignal;
  /** 서버가 받아들여 응답이 열렸다 */
  onOpen: () => void;
  /** closed 를 뺀 메시지 하나 */
  onMessage: (message: SseMessage) => void;
};

export async function readTableStream(options: StreamOptions): Promise<StreamEnd> {
  let response: Response;
  try {
    response = await fetch(streamUrl(options.tableId, options.cursor), {
      headers: streamHeaders(options.lastEventId),
      credentials: 'same-origin',
      signal: options.signal,
    });
  } catch (error) {
    return options.signal.aborted ? { kind: 'aborted' } : endOfFailure(error);
  }
  if (response.status === 401) return { kind: 'unauthorized' };
  if (!response.ok || !response.body) return { kind: 'http-error', status: response.status };
  options.onOpen();
  return readBody(response.body, options);
}

function streamUrl(tableId: string, cursor: StreamCursor): string {
  const query = new URLSearchParams({
    events_after: String(cursor.events),
    messages_after: String(cursor.messages),
    whispers_after: String(cursor.whispers),
  });
  return `/api/v1/game/tables/${encodeURIComponent(tableId)}/stream?${query}`;
}

function streamHeaders(lastEventId: string | null): Headers {
  const headers = new Headers({ Accept: 'text/event-stream' });
  const token = getSession()?.accessToken;
  if (token !== undefined) headers.set('Authorization', `Bearer ${token}`);
  if (lastEventId) headers.set('Last-Event-ID', lastEventId);
  return headers;
}

/** 본문을 끝까지 읽는다. closed 를 받으면 그 까닭으로, 그냥 끝나거나 끊기면 disconnected 로 끝난다 */
async function readBody(body: ReadableStream<Uint8Array>, options: StreamOptions): Promise<StreamEnd> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return { kind: 'disconnected' };
      const chunk = splitSse(buffer + decoder.decode(value, { stream: true }));
      buffer = chunk.rest;
      for (const message of chunk.messages) {
        if (message.event === 'closed') return { kind: 'closed', reason: closedReason(message.data) };
        options.onMessage(message);
      }
    }
  } catch (error) {
    return options.signal.aborted ? { kind: 'aborted' } : endOfFailure(error);
  } finally {
    reader.releaseLock();
  }
}

function closedReason(data: string): string {
  try {
    const parsed: unknown = JSON.parse(data);
    const reason = (parsed as { reason?: unknown } | null)?.reason;
    return typeof reason === 'string' ? reason : 'unknown';
  } catch {
    return 'unknown';
  }
}

/** 연결이 끊겼다(네트워크, 서버가 그냥 닫음). 쓰는 쪽이 잠깐 쉬었다가 다시 붙는다 */
function endOfFailure(error: unknown): StreamEnd {
  if (error instanceof DOMException && error.name === 'AbortError') return { kind: 'aborted' };
  return { kind: 'disconnected' };
}
