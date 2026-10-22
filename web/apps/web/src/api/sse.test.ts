// web/apps/web/src/api/sse.test.ts
// SSE 의 글을 메시지로 나누는지, 받은 조각이 메시지 중간에서 끊겨도 이어 붙이는지 본다.

import { describe, expect, it } from 'vitest';
import { splitSse } from './sse';

describe('splitSse', () => {
  it('빈 줄까지를 메시지 하나로 읽고, id 가 없는 메시지와 주석을 가른다', () => {
    const chunk = splitSse(
      ': connected\n\nid: 17-5-2\nevent: table_event\ndata: {"sequence": 17}\n\nevent: typing\ndata: {"user_id": "u"}\n\n: ping\n\n',
    );
    expect(chunk.messages).toEqual([
      { id: '17-5-2', event: 'table_event', data: '{"sequence": 17}' },
      { event: 'typing', data: '{"user_id": "u"}' },
    ]);
    expect(chunk.sawComment).toBe(true);
    expect(chunk.rest).toBe('');
  });

  it('끝나지 않은 메시지는 남겨 두었다가 다음 조각과 잇는다', () => {
    const first = splitSse('id: 1-0-0\nevent: chat_message\ndata: {"seq');
    expect(first.messages).toEqual([]);
    const second = splitSse(first.rest + 'uence": 1}\n\n');
    expect(second.messages).toEqual([{ id: '1-0-0', event: 'chat_message', data: '{"sequence": 1}' }]);
  });

  it('CRLF 줄 끝과 여러 줄의 data 를 받는다', () => {
    const chunk = splitSse('event: closed\r\ndata: {"reason":\r\ndata: "table_ended"}\r\n\r\n');
    expect(chunk.messages).toEqual([{ event: 'closed', data: '{"reason":\n"table_ended"}' }]);
  });

  it('event 가 없으면 message 다', () => {
    expect(splitSse('data: x\n\n').messages).toEqual([{ event: 'message', data: 'x' }]);
  });
});
