// board-server/test/spans.ts

/**
 * 테스트가 남긴 span 을 메모리에 모은다. 단위 테스트(src/**\/*.spec.ts)와 앱 테스트가 함께 쓴다.
 *
 * 서버가 쓰는 것과 같은 규칙(SAMPLER, 할 일 없는 바퀴를 버리는 DropIdleRounds)으로 만든다. 보내기만 메모리로 바꾼다.
 * 보내기를 묶지 않고 끝나는 대로 넘긴다(SimpleSpanProcessor). 테스트가 기다리지 않고 바로 읽는다.
 */

import { Span, TracerProvider as ApiTracerProvider } from '@opentelemetry/api';
import {
  InMemorySpanExporter,
  ReadableSpan,
  SimpleSpanProcessor,
  TracerProvider,
} from '@opentelemetry/sdk-trace';
import { DropIdleRounds } from '../src/observability/idle-rounds.js';
import { useProvider } from '../src/observability/spans.js';
import { SAMPLER } from '../src/observability/tracing.js';

/** 남긴 span 을 모으는 것. */
export class SpanRecorder {
  readonly exporter = new InMemorySpanExporter();
  readonly provider = new TracerProvider({
    sampler: SAMPLER,
    spanProcessors: [
      new DropIdleRounds(new SimpleSpanProcessor({ exporter: this.exporter })),
    ],
  });
  private previous: ApiTracerProvider | undefined;

  /** 이것을 끼운다. 앞의 것을 기억한다. */
  start(): void {
    this.previous = useProvider(this.provider);
  }

  /** 앞의 것으로 되돌리고 끈다. */
  async stop(): Promise<void> {
    if (this.previous !== undefined) {
      useProvider(this.previous);
    }
    await this.provider.shutdown();
  }

  /** 끝난 span 들. 끝난 차례다. */
  spans(): ReadableSpan[] {
    return this.exporter.getFinishedSpans();
  }

  /** 이 이름의 span 들. */
  named(name: string): ReadableSpan[] {
    return this.spans().filter((span) => span.name === name);
  }

  /** 이 이름의 span 하나. 하나가 아니면 실패한다. */
  only(name: string): ReadableSpan {
    const found = this.named(name);
    expect(found).toHaveLength(1);
    return found[0];
  }

  /** 모은 것을 비운다. */
  clear(): void {
    this.exporter.reset();
  }
}

/** 이 테스트 파일이 도는 동안 span 을 모은다. 테스트마다 비운다. */
export function recordSpans(): SpanRecorder {
  const recorder = new SpanRecorder();
  beforeAll(() => recorder.start());
  afterEach(() => recorder.clear());
  afterAll(() => recorder.stop());
  return recorder;
}

/** span 의 추적 번호. */
export function traceIdOf(span: ReadableSpan | Span): string {
  return span.spanContext().traceId;
}

/** span 의 번호. */
export function spanIdOf(span: ReadableSpan | Span): string {
  return span.spanContext().spanId;
}

/** span 의 부모의 번호. 부모가 없으면 undefined 다. */
export function parentIdOf(span: ReadableSpan): string | undefined {
  return span.parentSpanContext?.spanId;
}
