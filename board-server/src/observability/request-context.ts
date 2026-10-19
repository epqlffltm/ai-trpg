// board-server/src/observability/request-context.ts

/**
 * 지금 처리 중인 요청이나 작업의 식별자를 들고 있는 곳.
 *
 * Node 의 AsyncLocalStorage 에 둔다. 함수마다 인자로 넘기지 않아도, 같은 요청을 처리하는 코드 어디서든
 * 로그에 식별자가 붙는다. 요청마다 값을 따로 들고 있어서, 동시에 처리되는 요청끼리 섞이지 않는다.
 * 파이썬 서버들의 contextvars 와 같은 자리다.
 *
 * 요청에는 request_id, 작업(발송함의 알림을 보내는 한 바퀴)에는 job_id 가 걸린다. 둘이 함께 걸리지 않는다.
 */

import { AsyncLocalStorage } from 'node:async_hooks';
import { formatTraceparent, Trace, TRACEPARENT_HEADER } from './identifiers.js';
import { spanTraceparent } from './spans.js';

/** 요청 하나를 처리하는 동안 걸어 두는 값. */
export interface RequestContext {
  readonly requestId: string;
  readonly trace: Trace;
}

/** 작업 한 바퀴가 도는 동안 걸어 두는 값. */
export interface JobContext {
  readonly jobId: string;
  readonly trace: Trace;
}

/** 걸어 두는 것. 요청이거나 작업이다 */
export type WorkContext = RequestContext | JobContext;

/** 로그에 싣는 식별자들. 칸 이름은 규격의 것이다. */
export interface ContextIds {
  request_id?: string;
  job_id?: string;
  trace_id?: string;
}

const storage = new AsyncLocalStorage<WorkContext>();

/** 요청 하나를 처리하는 동안 그 식별자들을 건다. work 와 거기서 이어지는 일들이 그 안에서 돈다. */
export function runInRequest<Result>(
  context: RequestContext,
  work: () => Result,
): Result {
  return storage.run(context, work);
}

/** 작업 한 바퀴가 도는 동안 그 식별자들을 건다(observability/jobs.ts). */
export function runInJob<Result>(
  context: JobContext,
  work: () => Result,
): Result {
  return storage.run(context, work);
}

/** 지금 걸려 있는 요청이나 작업. 없으면 undefined 다. */
export function currentWork(): WorkContext | undefined {
  return storage.getStore();
}

/** 걸어 둔 것의 식별자들을 로그에 싣는 모양으로 바꾼다. */
export function idsOf(context: WorkContext | undefined): ContextIds {
  if (context === undefined) {
    return {};
  }
  if ('jobId' in context) {
    return { job_id: context.jobId, trace_id: context.trace.traceId };
  }
  return { request_id: context.requestId, trace_id: context.trace.traceId };
}

/** 지금 걸려 있는 식별자들. 걸려 있지 않으면 비어 있다. 로그의 모든 줄에 붙는다. */
export function currentIds(): ContextIds {
  return idsOf(currentWork());
}

/**
 * 우리 서버끼리 부를 때 요청에 붙일 머리말. 추적을 이어 준다. 걸려 있는 추적이 없으면 비어 있다.
 *
 * 기록 중인 span 이 있으면 그 span 을 가리킨다. 받는 서버의 span 이 그 아래에 붙는다.
 * 부르는 쪽(observability/http-spans.ts)이 그 호출의 span 으로 다시 바꾼다.
 * request_id 는 넘기지 않는다. 받는 서버가 제 요청의 식별자를 따로 만든다. 둘은 trace_id 로 이어진다.
 * 밖의 서비스를 부를 때는 붙이지 않는다. 우리 안의 식별자를 밖에 내보낼 까닭이 없다.
 */
export function outgoingHeaders(): Record<string, string> {
  const fromSpan = spanTraceparent();
  if (fromSpan !== undefined) {
    return { [TRACEPARENT_HEADER]: fromSpan };
  }
  const context = currentWork();
  if (context === undefined) {
    return {};
  }
  return { [TRACEPARENT_HEADER]: formatTraceparent(context.trace) };
}
