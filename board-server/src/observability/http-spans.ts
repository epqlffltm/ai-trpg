// board-server/src/observability/http-spans.ts

/**
 * 다른 서버를 부르는 요청에 client span 을 거는 fetch. 공개키(auth/jwks.ts), 끊긴 세션의 목록(auth/session-revocations.ts),
 * 알림 서버(notifications/notification-client.ts)를 부르는 곳이 쓴다. Node 의 fetch 와 모양이 같다.
 *
 * 부모 span 이 기록 중일 때만 건다(요청이나 작업 안의 호출). 아니면 fetch 를 그대로 부른다.
 * 끊긴 세션의 목록을 30초마다 받는 것은 부모가 없어 span 이 없다. 저마다 새 추적이 되어 Tempo 를 메운다.
 *
 * traceparent 는 부르는 쪽이 붙였을 때만 이 span 을 가리키게 바꾼다. 우리 서버를 부르는 곳은 이미
 * outgoingHeaders() 를 붙인다. 어디가 우리 서버인지는 부르는 쪽이 안다. TRPG 서버와 같은 규칙이다.
 *
 * span 에는 메서드, 상대의 호스트 이름, 상태 코드만 싣는다. 주소의 경로, 머리말, 본문은 싣지 않는다.
 * 예외의 글도 싣지 않는다. 주소가 들어 있을 수 있다.
 */

import { Span, SpanKind, SpanStatusCode } from '@opentelemetry/api';
import { TRACEPARENT_HEADER } from './identifiers.js';
import { isRecording, traceparentOf, tracer } from './spans.js';

/** 서버의 잘못으로 보는 상태 코드의 시작 */
const SERVER_ERROR = 500;
/** client span 의 이름 앞부분. 메서드만 붙인다(HTTP POST) */
export const SPAN_NAME_PREFIX = 'HTTP ';
/** 닿지 못했을 때(연결 실패, 시간 초과) span 의 상태에 적는 설명 */
export const UNREACHABLE = 'unreachable';

/** 부르는 주소의 호스트 이름. 읽지 못하면 빈 글자다. */
export function hostOf(input: string | URL | Request): string {
  const url = input instanceof Request ? input.url : String(input);
  return URL.canParse(url) ? new URL(url).hostname : '';
}

/** 부르는 메서드. 적지 않았으면 GET 이다. */
export function methodOf(init: RequestInit | undefined): string {
  return (init?.method ?? 'GET').toUpperCase();
}

/** 부르는 쪽이 traceparent 를 붙였으면 이 span 을 가리키게 바꾼 요청. 붙이지 않았으면 그대로다. */
export function withSpanTraceparent(
  init: RequestInit | undefined,
  span: Span,
): RequestInit | undefined {
  const headers = new Headers(init?.headers);
  if (!headers.has(TRACEPARENT_HEADER)) {
    return init;
  }
  headers.set(TRACEPARENT_HEADER, traceparentOf(span));
  return { ...init, headers };
}

/** 받은 상태 코드를 적는다. 상대의 잘못(5xx)만 오류로 표시한다. 4xx 는 부른 쪽이 답을 보고 다룬다. */
export function recordStatus(span: Span, statusCode: number): void {
  span.setAttribute('http.response.status_code', statusCode);
  if (statusCode >= SERVER_ERROR) {
    span.setStatus({ code: SpanStatusCode.ERROR });
  }
}

/** span 안에서 부른다. 답의 본문은 span 이 끝난 뒤에 읽는다(답을 기다린 시간만 잰다). */
async function fetchInSpan(
  span: Span,
  input: string | URL | Request,
  init: RequestInit | undefined,
): Promise<Response> {
  try {
    const response = await fetch(input, withSpanTraceparent(init, span));
    recordStatus(span, response.status);
    return response;
  } catch (error) {
    span.setStatus({ code: SpanStatusCode.ERROR, message: UNREACHABLE });
    throw error;
  } finally {
    span.end();
  }
}

/** client span 을 거는 fetch. 부모 span 이 없으면 fetch 그대로다. */
export const tracedFetch: typeof fetch = (input, init) => {
  if (!isRecording()) {
    return fetch(input, init);
  }
  const method = methodOf(init);
  return tracer().startActiveSpan(
    SPAN_NAME_PREFIX + method,
    {
      kind: SpanKind.CLIENT,
      attributes: {
        'http.request.method': method,
        'server.address': hostOf(input),
      },
    },
    (span) => fetchInSpan(span, input, init),
  );
};
