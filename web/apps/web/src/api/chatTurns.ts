// web/apps/web/src/api/chatTurns.ts
// 답을 받는 SSE 의 본문을 끝까지 읽어 메시지를 하나씩 넘긴다. 다시 붙지 않는다(서버는 끊겨도 끝까지 저장하고, 화면이 대화를 다시 읽는다).
// 메시지의 모양은 chat-server/app/turns/schemas.py 다. 읽기만 하고 뜻은 화면(pages/chat/conversation/turnState.ts)이 정한다.

import { splitSse, type SseMessage } from './sse';

/** 끝난 까닭. ended 는 본문이 끝났다(done 이나 failed 뒤), cut 은 그 전에 끊겼다, aborted 는 화면이 닫았다 */
export type TurnStreamEnd = 'ended' | 'cut' | 'aborted';

export async function readTurnStream(response: Response, onMessage: (message: SseMessage) => void, signal: AbortSignal): Promise<TurnStreamEnd> {
  if (!response.body) return 'cut';
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finished = false;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return finished ? 'ended' : 'cut';
      const chunk = splitSse(buffer + decoder.decode(value, { stream: true }));
      buffer = chunk.rest;
      for (const message of chunk.messages) {
        finished ||= message.event === 'done' || message.event === 'failed';
        onMessage(message);
      }
    }
  } catch {
    return signal.aborted ? 'aborted' : 'cut';
  } finally {
    reader.releaseLock();
  }
}
