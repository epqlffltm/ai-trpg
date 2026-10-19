// board-server/src/observability/idle-rounds.spec.ts

/**
 * 할 일이 없던 작업의 추적을 버리는 것(idle-rounds.ts)을 검증한다.
 * 메모리에 모으는 것(test/spans.ts)이 서버와 같은 DropIdleRounds 를 거친다.
 */

import { SpanStatusCode } from '@opentelemetry/api';
import {
  InMemorySpanExporter,
  SimpleSpanProcessor,
} from '@opentelemetry/sdk-trace';
import { recordSpans } from '../../test/spans.js';
import { DropIdleRounds } from './idle-rounds.js';
import { inJobSpan, recordHandled, tracer } from './spans.js';

const recorder = recordSpans();

/** 작업 한 바퀴. 안에서 쿼리 하나만큼의 span 을 남기고, 처리한 수를 싣는다(undefined 면 싣지 않는다). */
function round(handled: number | undefined, fail = false): Promise<void> {
  return inJobSpan('notification.send', 'job-1', () => {
    tracer().startSpan('db SELECT outgoing_notifications').end();
    if (handled !== undefined) {
      recordHandled(handled);
    }
    return fail ? Promise.reject(new Error('DB 가 없다')) : Promise.resolve();
  });
}

describe('DropIdleRounds', () => {
  it('할 일이 없던 바퀴는 그 아래의 span 까지 통째로 버린다', async () => {
    await round(0);

    expect(recorder.spans()).toEqual([]);
  });

  it('한 일이 있는 바퀴는 아래의 span 과 함께 보낸다', async () => {
    await round(2);

    expect(recorder.spans().map((span) => span.name)).toEqual([
      'db SELECT outgoing_notifications',
      'notification.send',
    ]);
  });

  it('실패한 바퀴는 처리한 수가 0 이어도 보낸다', async () => {
    await expect(round(0, true)).rejects.toThrow();

    const job = recorder.only('notification.send');
    expect(job.status.code).toBe(SpanStatusCode.ERROR);
    expect(recorder.spans()).toHaveLength(2);
  });

  it('처리한 수를 싣지 않은 작업은 보낸다', async () => {
    await round(undefined);

    expect(recorder.spans()).toHaveLength(2);
  });

  it('작업이 아닌 추적(요청)은 들지 않고 끝나는 대로 넘긴다', () => {
    tracer().startActiveSpan('GET /api/v1/board/boards', (request) => {
      tracer().startSpan('db SELECT boards').end();
      expect(recorder.named('db SELECT boards')).toHaveLength(1);
      request.end();
    });

    expect(recorder.spans()).toHaveLength(2);
  });

  it('요청 안에서 돈 작업은 요청의 추적이라 들지 않는다', async () => {
    await tracer().startActiveSpan('POST /api/v1/board/posts', async (span) => {
      await round(0);
      span.end();
    });

    expect(recorder.spans()).toHaveLength(3);
  });

  it('끌 때 끝나지 않은 작업의 추적을 버리고 inner 를 끈다', async () => {
    const exporter = new InMemorySpanExporter();
    const processor = new DropIdleRounds(new SimpleSpanProcessor({ exporter }));
    const inner = vi.spyOn(SimpleSpanProcessor.prototype, 'shutdown');

    await processor.forceFlush();
    await processor.shutdown();

    expect(inner).toHaveBeenCalledOnce();
    inner.mockRestore();
  });
});
