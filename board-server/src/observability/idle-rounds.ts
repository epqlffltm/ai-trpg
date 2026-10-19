// board-server/src/observability/idle-rounds.ts

/**
 * 할 일이 없던 작업의 추적을 보내지 않는 것. span 을 보내는 것(BatchSpanProcessor) 앞에 끼운다(tracing.ts).
 * 인증 서버의 것(auth-server/observability/idle_rounds.py)과 같은 규칙이다.
 *
 * 발송함의 알림을 보내는 작업은 5초마다 한 바퀴 돈다. 대개 보낼 알림이 없다. 바퀴마다 추적을 남기면
 * 하루에 만칠천 개가 넘고, Tempo 의 검색이 빈 바퀴로 메워진다. 한 일이 있는 바퀴와 실패한 바퀴만 남긴다.
 *
 * 작업의 span 이 끝나야 할 일이 있었는지 안다(spans.recordHandled). 그 아래의 span(쿼리, 알림 서버를 부른 것)은
 * 먼저 끝난다. 그래서 작업의 추적에 든 span 은 작업의 span 이 끝날 때까지 들고 있다가 함께 보내거나 함께 버린다.
 * 작업이 아닌 추적(요청)은 들지 않고 바로 넘긴다.
 */

import { Context, SpanStatusCode } from '@opentelemetry/api';
import { ReadableSpan, Span, SpanProcessor } from '@opentelemetry/sdk-trace';
import { ATTRIBUTE_HANDLED, ATTRIBUTE_JOB_ID } from './spans.js';

/** 부모 없이 시작한 작업의 span 인가. 그 추적은 끝날 때까지 들고 있는다. */
export function isJobRoot(span: ReadableSpan): boolean {
  return (
    span.parentSpanContext === undefined && ATTRIBUTE_JOB_ID in span.attributes
  );
}

/** 할 일이 없던 바퀴인가. 처리한 수가 0 이고 실패하지 않았다. 처리한 수를 적지 않은 작업은 남긴다. */
export function isIdle(span: ReadableSpan): boolean {
  return (
    span.attributes[ATTRIBUTE_HANDLED] === 0 &&
    span.status.code !== SpanStatusCode.ERROR
  );
}

/** 할 일이 없던 작업의 추적을 버리고, 나머지는 inner 에 넘긴다. */
export class DropIdleRounds implements SpanProcessor {
  /** 작업의 추적마다 먼저 끝난 span 들. 작업의 span 이 끝나면 비운다 */
  private readonly held = new Map<string, ReadableSpan[]>();

  constructor(private readonly inner: SpanProcessor) {}

  /** 작업의 span 이 시작하면 그 추적을 들고 있기 시작한다. */
  onStart(span: Span, parentContext: Context): void {
    if (isJobRoot(span)) {
      this.held.set(span.spanContext().traceId, []);
    }
    this.inner.onStart(span, parentContext);
  }

  /** 끝난 span 을 들고 있거나, 작업이 끝났으면 함께 넘기거나 버린다. */
  onEnd(span: ReadableSpan): void {
    const released = this.release(span);
    if (released === undefined || (isJobRoot(span) && isIdle(span))) {
      return;
    }
    for (const each of released) {
      this.inner.onEnd(each);
    }
  }

  /**
   * 지금 넘길 span 들. 작업의 추적에 든 span 이면 들고 있고 undefined 를 돌려준다.
   *
   * 작업의 span 이면 들고 있던 것과 그것을 함께 돌려준다. 작업이 아닌 추적의 span 은 그것 하나다.
   */
  release(span: ReadableSpan): ReadableSpan[] | undefined {
    const traceId = span.spanContext().traceId;
    const held = this.held.get(traceId);
    if (held === undefined) {
      return [span];
    }
    if (!isJobRoot(span)) {
      held.push(span);
      return undefined;
    }
    this.held.delete(traceId);
    return [...held, span];
  }

  /** 끝나지 않은 작업의 추적은 버리고 inner 를 끈다. */
  shutdown(): Promise<void> {
    this.held.clear();
    return this.inner.shutdown();
  }

  /** inner 가 모아 둔 것을 보낸다. */
  forceFlush(): Promise<void> {
    return this.inner.forceFlush();
  }
}
