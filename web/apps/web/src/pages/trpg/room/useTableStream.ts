// web/apps/web/src/pages/trpg/room/useTableStream.ts
// 테이블 방에 있는 동안 스트림을 붙잡고 있는다. 끊기면 다시 붙고(streamPolicy.ts), 화면을 떠나면 끊는다.
//
// 붙는 순서: 채팅의 끝부분을 읽은 뒤(채팅의 마지막 번호), 이벤트와 쪽지의 마지막 번호를 읽고 그 뒤부터 붙는다.
// 다시 붙을 때는 마지막으로 받은 id 를 Last-Event-ID 로 보낸다. 같은 것이 두 번 오지 않는다.
// 받은 것은 handlers 로 넘긴다. 열릴 때마다 onOpen 을 부른다(그사이 놓친 테이블의 변화를 다시 읽게).

import { useEffect, useRef, useState } from 'react';
import { ApiError } from '../../../api/errors';
import { refreshSession } from '../../../api/refresh';
import { fetchStreamCursor } from '../../../api/tableRoom';
import { readTableStream, type StreamCursor, type StreamEnd } from '../../../api/tableStream';
import type { ChatMessage, TableEvent } from '../../../api/types';
import { nextStep, routeMessage, type StopReason } from './streamPolicy';

export type StreamStatus =
  | { state: 'connecting' }
  | { state: 'open' }
  | { state: 'reconnecting'; inMs: number }
  | { state: 'stopped'; reason: StopReason };

export type StreamHandlers = {
  onOpen: () => void;
  onEvent: (event: TableEvent) => void;
  onChat: (message: ChatMessage) => void;
  onTyping: (userId: string) => void;
  onStop: (reason: StopReason) => void;
};

/** chatCursor: 화면이 읽은 채팅의 마지막 번호. null 이면 아직 읽는 중이라 붙지 않는다 */
export function useTableStream(tableId: string, chatCursor: number | null, handlers: StreamHandlers): StreamStatus {
  const [status, setStatus] = useState<StreamStatus>({ state: 'connecting' });
  const latest = useRef(handlers);
  useEffect(() => {
    latest.current = handlers;
  });
  const ready = chatCursor !== null;

  useEffect(() => {
    if (!ready) return undefined;
    const controller = new AbortController();
    void runStream(tableId, chatCursor, controller.signal, setStatus, () => latest.current);
    return () => controller.abort();
    // 채팅의 번호는 처음 붙을 때만 쓴다. 그 뒤로는 Last-Event-ID 로 잇는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tableId, ready]);

  return status;
}

async function runStream(
  tableId: string,
  chatCursor: number,
  signal: AbortSignal,
  setStatus: (status: StreamStatus) => void,
  handlers: () => StreamHandlers,
): Promise<void> {
  let cursor: StreamCursor | null = null;
  let lastEventId: string | null = null;
  let failures = 0;
  while (!signal.aborted) {
    const found: StreamCursor | StreamEnd = cursor ?? (await cursorOrEnd(tableId, chatCursor, signal));
    let end: StreamEnd;
    if ('kind' in found) {
      end = found;
    } else {
      cursor = found;
      end = await readTableStream({
        tableId,
        cursor: found,
        lastEventId,
        signal,
        onOpen: () => {
          failures = 0;
          setStatus({ state: 'open' });
          handlers().onOpen();
        },
        onMessage: (message) => {
          if (message.id) lastEventId = message.id;
          deliver(message, handlers());
        },
      });
    }
    if (signal.aborted) return;
    failures += 1;
    const step = nextStep(end, failures, Math.random());
    if (step.action === 'stop') return stop(step.reason, setStatus, handlers);
    const delayMs = step.action === 'refresh-token' ? await renewToken() : step.delayMs;
    if (delayMs === null) return stop('signed_out', setStatus, handlers);
    if (delayMs > 0) {
      setStatus({ state: 'reconnecting', inMs: delayMs });
      await sleep(delayMs, signal);
    }
  }
}

/** 처음 붙을 번호. 읽지 못하면 그 까닭을 스트림이 끝난 것처럼 돌려준다(404 면 앉아 있지 않다) */
async function cursorOrEnd(tableId: string, chatCursor: number, signal: AbortSignal): Promise<StreamCursor | StreamEnd> {
  try {
    return await fetchStreamCursor(tableId, chatCursor, signal);
  } catch (error) {
    if (signal.aborted) return { kind: 'aborted' };
    if (error instanceof ApiError) return { kind: 'http-error', status: error.status };
    return { kind: 'disconnected' };
  }
}

/** 토큰을 갱신한다. 되면 바로(0), 서버가 잠시 답하지 않으면 잠깐 뒤에, 로그인이 끝났으면 null */
async function renewToken(): Promise<number | null> {
  try {
    return (await refreshSession()) === null ? null : 0;
  } catch {
    const step = nextStep({ kind: 'disconnected' }, 1, Math.random());
    return step.action === 'reconnect' ? step.delayMs : 0;
  }
}

function deliver(message: Parameters<typeof routeMessage>[0], handlers: StreamHandlers): void {
  const routed = routeMessage(message);
  if (routed.kind === 'event') handlers.onEvent(routed.event);
  else if (routed.kind === 'chat') handlers.onChat(routed.message);
  else if (routed.kind === 'typing') handlers.onTyping(routed.userId);
}

function stop(reason: StopReason, setStatus: (status: StreamStatus) => void, handlers: () => StreamHandlers): void {
  setStatus({ state: 'stopped', reason });
  handlers().onStop(reason);
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener('abort', () => {
      clearTimeout(timer);
      resolve();
    });
  });
}
