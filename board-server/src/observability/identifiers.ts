// board-server/src/observability/identifiers.ts

/**
 * 요청을 가리키는 식별자의 규칙. 다른 것을 모르는 순수한 함수들이다. 규격은 저장소 루트의 docs/observability.md 에 있다.
 *
 * 식별자는 셋이다.
 *   - request_id: 이 서버가 받은 요청 하나. 밖에서 준 값이 형식에 맞으면 그대로 쓰고, 아니면 새로 만든다.
 *   - trace_id: 한 사용자의 요청이 여러 서버를 거칠 때 그 전체. W3C Trace Context 의 trace-id 와 같은 모양이다.
 *   - job_id: 요청과 따로 도는 작업 하나. 발송함의 알림을 보내는 한 바퀴다(observability/jobs.ts).
 *
 * 식별자는 기록을 서로 잇는 데만 쓴다. 누구인지, 해도 되는지를 판단하는 데 쓰지 않는다. 밖에서 정할 수 있는 값이다.
 *
 * 밖에서 받은 값은 형식을 먼저 본다. 로그에 그대로 적히는 값이라, 줄바꿈이나 제어 문자가 섞이면
 * 가짜 로그 줄을 끼워 넣을 수 있다. 형식에 맞지 않으면 고쳐 쓰지 않고 버린다.
 */

import { randomBytes, randomUUID } from 'node:crypto';

/** 요청 식별자를 주고받는 머리말. 응답에도 같은 이름으로 돌려준다 */
export const REQUEST_ID_HEADER = 'X-Request-ID';
/** 추적 정보를 주고받는 머리말. W3C Trace Context 의 이름 그대로다. OpenTelemetry 도 같은 머리말을 쓴다 */
export const TRACEPARENT_HEADER = 'traceparent';

/** 밖에서 받는 요청 식별자의 모양. 영문, 숫자, 점, 밑줄, 붙임표로 8자에서 64자. UUID 가 여기에 든다 */
const REQUEST_ID = /^[A-Za-z0-9._-]{8,64}$/;
/** traceparent 의 모양(버전 00). 버전-추적 식별자(32자)-부모 식별자(16자)-표시(2자). 모두 소문자 16진수다 */
const TRACEPARENT = /^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$/;
/** 0 으로만 된 값. 추적 식별자와 부모 식별자는 0 으로만 될 수 없다 */
const ALL_ZERO = /^0+$/;
/** 머리말 값을 이보다 길게 주면 형식을 보지도 않고 버린다 */
const MAX_HEADER_LENGTH = 128;
/** span 없이 새로 시작하는 추적의 표시. "기록하지 않음"이다. span 이 있으면 그 표시를 쓴다(spans.ts) */
const NOT_SAMPLED = '00';

/** 서버들을 거치는 흐름 하나. traceId 는 소문자 16진수 32자, flags 는 받은 표시를 그대로 넘기려고 둔다. */
export interface Trace {
  readonly traceId: string;
  readonly flags: string;
}

/** traceparent 를 나눈 것. 모두 소문자 16진수다. */
export interface TraceparentParts {
  readonly traceId: string;
  readonly parentId: string;
  readonly flags: string;
}

/** 값이 형식을 볼 만한 글자인가. 글자가 아니거나 너무 길면 아니다. 머리말이 여러 번 오면 배열로 온다. */
function isShortText(value: unknown): value is string {
  return typeof value === 'string' && value.length <= MAX_HEADER_LENGTH;
}

/** 밖에서 받은 요청 식별자가 형식에 맞으면 그대로 돌려준다. 없거나 맞지 않으면 undefined 다. */
export function acceptRequestId(value: unknown): string | undefined {
  return isShortText(value) && REQUEST_ID.test(value) ? value : undefined;
}

/** 새 작업 식별자. UUID 다. */
export function newJobId(): string {
  return randomUUID();
}

/** 새 요청 식별자. UUID 다. */
export function newRequestId(): string {
  return randomUUID();
}

/** 이 요청의 식별자를 정한다. 밖에서 받은 값이 쓸 만하면 그것을, 아니면 새것을 쓴다. */
export function requestIdFrom(value: unknown): string {
  return acceptRequestId(value) ?? newRequestId();
}

/**
 * traceparent 머리말을 셋으로 나눈다. 없거나 형식에 맞지 않으면 undefined 다.
 *
 * 버전 00 만 읽는다. 받은 요청의 span 의 부모(spans.ts 의 remoteParent)와 로그의 추적이 같은 규칙으로 읽는다.
 */
export function traceparentParts(value: unknown): TraceparentParts | undefined {
  if (!isShortText(value)) {
    return undefined;
  }
  const match = TRACEPARENT.exec(value.trim());
  if (match === null || ALL_ZERO.test(match[1]) || ALL_ZERO.test(match[2])) {
    return undefined;
  }
  return { traceId: match[1], parentId: match[2], flags: match[3] };
}

/** traceparent 머리말에서 추적을 읽는다. 없거나 형식에 맞지 않으면 undefined 다. 부모 식별자는 버린다. */
export function parseTraceparent(value: unknown): Trace | undefined {
  const parts = traceparentParts(value);
  return parts === undefined
    ? undefined
    : { traceId: parts.traceId, flags: parts.flags };
}

/** 새 추적을 시작한다. */
export function newTrace(): Trace {
  return { traceId: randomBytes(16).toString('hex'), flags: NOT_SAMPLED };
}

/** 이 요청의 추적을 정한다. 밖에서 받은 것이 쓸 만하면 이어 가고, 아니면 새로 시작한다. */
export function traceFrom(value: unknown): Trace {
  return parseTraceparent(value) ?? newTrace();
}

/**
 * span 없이 다른 서버에 보낼 traceparent 값을 만든다.
 *
 * 부모 식별자는 부를 때마다 새로 만든다. 받는 쪽은 추적 식별자만 이어 쓴다.
 * span 이 있으면 그 span 의 번호를 보낸다(request-context.ts 의 outgoingHeaders).
 */
export function formatTraceparent(trace: Trace): string {
  return `00-${trace.traceId}-${randomBytes(8).toString('hex')}-${trace.flags}`;
}
