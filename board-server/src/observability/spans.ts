// board-server/src/observability/spans.ts

/**
 * span 을 만들고 읽는 곳. OpenTelemetry 의 API 만 쓴다. 보내는 것(SDK)은 tracing.ts 가 만든다.
 * 규격은 저장소 루트의 docs/observability.md 의 "3. 추적"에 있다. 알림 서버(app/observability/spans.py)와 같은 모양이다.
 *
 * span 을 만드는 것(TracerProvider)은 OpenTelemetry 의 전역에 두지 않고 여기에 하나 둔다(useProvider).
 * 전역은 프로세스에 한 번만 바꿀 수 있어서 테스트가 바꿔 끼우지 못한다. 처음에는 아무것도 남기지 않는 것(noop)이다.
 *
 * 지금의 span 은 Node 의 AsyncLocalStorage 로 들고 있다(context manager). 이것은 전역에 한 번 건다.
 * 걸지 않으면 span 안에서 부른 쿼리와 호출이 그 span 을 부모로 찾지 못한다.
 */

import {
  context,
  Context,
  ROOT_CONTEXT,
  Span,
  SpanKind,
  SpanStatusCode,
  trace,
  Tracer,
  TracerProvider,
} from '@opentelemetry/api';
import { AsyncLocalStorageContextManager } from '@opentelemetry/context-async-hooks';
import { Trace, traceparentParts } from './identifiers.js';

/** span 을 만든 코드의 이름(instrumentation scope). 서버의 이름과 같다 */
export const SCOPE_NAME = 'board-server';
/** 요청의 span 에 싣는 요청 식별자, 작업의 span 에 싣는 작업 식별자와 결과. 로그의 칸 이름과 같다 */
export const ATTRIBUTE_REQUEST_ID = 'request_id';
export const ATTRIBUTE_JOB_ID = 'job_id';
export const ATTRIBUTE_RESULT = 'result';
/** 작업이 한 바퀴에 처리한 수. 0 이면 할 일이 없던 바퀴다(idle-rounds.ts) */
export const ATTRIBUTE_HANDLED = 'handled';
/** 작업이 실패했을 때 span 의 상태에 적는 설명. 로그의 error_code 와 같다 */
export const JOB_FAILED_ERROR_CODE = 'job.failed';

/** 지금 쓰는 TracerProvider. 처음에는 전역의 것(아무것도 남기지 않는다)이다 */
let provider: TracerProvider = trace.getTracerProvider();
/** 지금의 span 을 들고 있는 것을 전역에 걸었는가 */
let contextManagerInstalled = false;

/** 지금의 span 을 들고 있는 것(AsyncLocalStorage)을 전역에 건다. 여러 번 불러도 한 번만 건다. */
export function installContextManager(): void {
  if (contextManagerInstalled) {
    return;
  }
  context.setGlobalContextManager(
    new AsyncLocalStorageContextManager().enable(),
  );
  contextManagerInstalled = true;
}

/** span 을 만드는 것을 바꿔 끼운다. 앞의 것을 돌려준다. 서버가 뜰 때(tracing.ts)와 테스트가 부른다. */
export function useProvider(next: TracerProvider): TracerProvider {
  installContextManager();
  const previous = provider;
  provider = next;
  return previous;
}

/** span 을 만드는 것. */
export function tracer(): Tracer {
  return provider.getTracer(SCOPE_NAME);
}

/** 지금 기록 중인 span 이 있는가. 그 아래에만 쿼리와 호출의 span 을 건다. */
export function isRecording(): boolean {
  return trace.getActiveSpan()?.isRecording() ?? false;
}

/**
 * 받은 traceparent 를 부모로 가진 문맥. 형식에 맞지 않으면 부모가 없는 문맥이다(새 추적).
 *
 * flags 가 00(기록하지 않음)이어도 부모로 쓴다. 남길지는 tracing.ts 의 SAMPLER 가 정한다(모두 남긴다).
 */
export function remoteParent(header: unknown): Context {
  const parts = traceparentParts(header);
  if (parts === undefined) {
    return ROOT_CONTEXT;
  }
  return trace.setSpanContext(ROOT_CONTEXT, {
    traceId: parts.traceId,
    spanId: parts.parentId,
    traceFlags: Number.parseInt(parts.flags, 16),
    isRemote: true,
  });
}

/** span 의 표시(flags)를 두 자리 16진수로. */
function flagsOf(span: Span): string {
  return span.spanContext().traceFlags.toString(16).padStart(2, '0');
}

/** 기록 중인 지금의 span. 없으면 undefined 다. */
function recordingSpan(): Span | undefined {
  const span = trace.getActiveSpan();
  return span?.isRecording() ? span : undefined;
}

/** 지금의 span 의 추적. 로그의 trace_id 가 이것을 쓴다. 기록 중인 span 이 없으면 undefined 다. */
export function spanTrace(): Trace | undefined {
  const span = recordingSpan();
  if (span === undefined) {
    return undefined;
  }
  return { traceId: span.spanContext().traceId, flags: flagsOf(span) };
}

/** span 을 가리키는 traceparent. 받는 서버의 span 이 이 span 아래에 붙는다. */
export function traceparentOf(span: Span): string {
  const { traceId, spanId } = span.spanContext();
  return `00-${traceId}-${spanId}-${flagsOf(span)}`;
}

/** 지금의 span 을 가리키는 traceparent. 기록 중인 span 이 없으면 undefined 다. */
export function spanTraceparent(): string | undefined {
  const span = recordingSpan();
  return span === undefined ? undefined : traceparentOf(span);
}

/** 지금의 span 에 속성 하나를 싣는다. span 이 없으면 아무것도 하지 않는다. */
export function tagCurrentSpan(key: string, value: string | number): void {
  trace.getActiveSpan()?.setAttribute(key, value);
}

/** 작업이 한 바퀴에 처리한 수를 지금의 span(작업의 span)에 싣는다. 0 이면 그 추적을 보내지 않는다(idle-rounds.ts). */
export function recordHandled(count: number): void {
  tagCurrentSpan(ATTRIBUTE_HANDLED, count);
}

/** 작업의 끝을 span 에 적는다. 실패면 오류로 표시한다. */
export function markJob(span: Span, failed: boolean): void {
  span.setAttribute(ATTRIBUTE_RESULT, failed ? 'server_error' : 'success');
  if (failed) {
    span.setStatus({
      code: SpanStatusCode.ERROR,
      message: JOB_FAILED_ERROR_CODE,
    });
  }
}

/**
 * 작업 한 바퀴의 span 안에서 work 를 돌린다. 이름은 operation(notification.send)이다.
 *
 * 걸린 span 이 있으면 그 아래에 놓이고, 없으면(타이머가 돌린 바퀴) 새 추적이다.
 * work 가 예외를 내면 오류로 표시하고 그대로 올린다. 예외의 글은 싣지 않는다.
 */
export function inJobSpan<Result>(
  operation: string,
  jobId: string,
  work: () => Promise<Result>,
): Promise<Result> {
  return tracer().startActiveSpan(
    operation,
    { kind: SpanKind.INTERNAL, attributes: { [ATTRIBUTE_JOB_ID]: jobId } },
    async (span) => {
      try {
        const result = await work();
        markJob(span, false);
        return result;
      } catch (error) {
        markJob(span, true);
        throw error;
      } finally {
        span.end();
      }
    },
  );
}
