// board-server/src/observability/request-context.ts

/**
 * 지금 처리 중인 요청의 식별자를 들고 있는 곳.
 *
 * Node 의 AsyncLocalStorage 에 둔다. 함수마다 인자로 넘기지 않아도, 같은 요청을 처리하는 코드 어디서든
 * 로그에 식별자가 붙는다. 요청마다 값을 따로 들고 있어서, 동시에 처리되는 요청끼리 섞이지 않는다.
 * 파이썬 서버들의 contextvars 와 같은 자리다.
 */

import { AsyncLocalStorage } from 'node:async_hooks';
import { formatTraceparent, Trace, TRACEPARENT_HEADER } from './identifiers.js';

/** 요청 하나를 처리하는 동안 걸어 두는 값. */
export interface RequestContext {
  readonly requestId: string;
  readonly trace: Trace;
}

/** 로그에 싣는 식별자들. 칸 이름은 규격의 것이다. */
export interface ContextIds {
  request_id?: string;
  trace_id?: string;
}

const storage = new AsyncLocalStorage<RequestContext>();

/** 요청 하나를 처리하는 동안 그 식별자들을 건다. work 와 거기서 이어지는 일들이 그 안에서 돈다. */
export function runInRequest<Result>(
  context: RequestContext,
  work: () => Result,
): Result {
  return storage.run(context, work);
}

/** 지금 걸려 있는 요청. 없으면 undefined 다. */
export function currentRequest(): RequestContext | undefined {
  return storage.getStore();
}

/** 요청의 식별자들을 로그에 싣는 모양으로 바꾼다. */
export function idsOf(context: RequestContext | undefined): ContextIds {
  if (context === undefined) {
    return {};
  }
  return { request_id: context.requestId, trace_id: context.trace.traceId };
}

/** 지금 걸려 있는 식별자들. 걸려 있지 않으면 비어 있다. 로그의 모든 줄에 붙는다. */
export function currentIds(): ContextIds {
  return idsOf(currentRequest());
}

/**
 * 우리 서버끼리 부를 때 요청에 붙일 머리말. 추적을 이어 준다. 걸려 있는 추적이 없으면 비어 있다.
 *
 * request_id 는 넘기지 않는다. 받는 서버가 제 요청의 식별자를 따로 만든다. 둘은 trace_id 로 이어진다.
 * 밖의 서비스를 부를 때는 붙이지 않는다. 우리 안의 식별자를 밖에 내보낼 까닭이 없다.
 */
export function outgoingHeaders(): Record<string, string> {
  const context = currentRequest();
  if (context === undefined) {
    return {};
  }
  return { [TRACEPARENT_HEADER]: formatTraceparent(context.trace) };
}
