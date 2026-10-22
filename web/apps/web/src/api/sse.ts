// web/apps/web/src/api/sse.ts
// SSE(Server-Sent Events)의 글을 메시지로 나눈다. 순수한 함수다. 받는 것(fetch)은 tableStream.ts 가 한다.
//
// 빈 줄까지가 메시지 하나다. 줄은 "이름: 값" 이고, ":" 로 시작하는 줄은 주석(: ping, : connected)이다.
// 쓰는 이름은 id, event, data 뿐이다(retry 는 쓰지 않는다. 다시 붙는 간격은 화면이 정한다).
// data 가 여러 줄이면 "\n" 으로 잇는다. 줄 끝은 \n, \r\n, \r 을 모두 받는다(SSE 규격).

export type SseMessage = {
  /** 여기까지 받았다는 표시. 저장하지 않는 메시지(typing, closed 같은 것)에는 없다 */
  id?: string;
  /** 없으면 "message" */
  event: string;
  data: string;
};

export type SseChunk = {
  messages: SseMessage[];
  /** 아직 빈 줄을 받지 못한 끝부분. 다음 조각의 앞에 붙인다 */
  rest: string;
  /** 주석을 하나라도 받았는가(: connected, : ping). 연결이 살아 있다는 표시다 */
  sawComment: boolean;
};

const MESSAGE_END = /\r\n\r\n|\n\n|\r\r/;

/** 받은 글(앞에 남은 것 + 새 조각)을 메시지와 남은 끝부분으로 나눈다 */
export function splitSse(buffer: string): SseChunk {
  const messages: SseMessage[] = [];
  let rest = buffer;
  let sawComment = false;
  let match = MESSAGE_END.exec(rest);
  while (match) {
    const block = rest.slice(0, match.index);
    rest = rest.slice(match.index + match[0].length);
    const parsed = parseBlock(block);
    sawComment ||= parsed.comment;
    if (parsed.message) messages.push(parsed.message);
    match = MESSAGE_END.exec(rest);
  }
  return { messages, rest, sawComment };
}

/** 메시지 하나(빈 줄 앞까지). data 가 없으면 메시지가 아니다(주석만 있는 묶음) */
function parseBlock(block: string): { message: SseMessage | null; comment: boolean } {
  let id: string | undefined;
  let event = 'message';
  const data: string[] = [];
  let comment = false;
  for (const line of block.split(/\r\n|\n|\r/)) {
    if (line.startsWith(':')) {
      comment = true;
      continue;
    }
    const [name, value] = fieldOf(line);
    if (name === 'id') id = value;
    else if (name === 'event') event = value;
    else if (name === 'data') data.push(value);
  }
  if (data.length === 0) return { message: null, comment };
  return { message: id === undefined ? { event, data: data.join('\n') } : { id, event, data: data.join('\n') }, comment };
}

/** "이름: 값" → [이름, 값]. 콜론 뒤의 빈칸 하나는 떼고, 콜론이 없으면 줄 전체가 이름이다 */
function fieldOf(line: string): [string, string] {
  const colon = line.indexOf(':');
  if (colon === -1) return [line, ''];
  const value = line.slice(colon + 1);
  return [line.slice(0, colon), value.startsWith(' ') ? value.slice(1) : value];
}
