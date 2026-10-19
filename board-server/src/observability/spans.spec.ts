// board-server/src/observability/spans.spec.ts

/**
 * span 을 만들고 읽는 곳(spans.ts)을 검증한다. 메모리에 모으는 것을 끼워 본다(test/spans.ts).
 */

import { context, SpanStatusCode } from '@opentelemetry/api';
import {
  parentIdOf,
  recordSpans,
  spanIdOf,
  traceIdOf,
} from '../../test/spans.js';
import {
  ATTRIBUTE_JOB_ID,
  ATTRIBUTE_RESULT,
  inJobSpan,
  isRecording,
  JOB_FAILED_ERROR_CODE,
  recordHandled,
  remoteParent,
  spanTrace,
  spanTraceparent,
  tagCurrentSpan,
  tracer,
} from './spans.js';

const TRACE_ID = '4bf92f3577b34da6a3ce929d0e0e4736';
const PARENT_ID = '00f067aa0ba902b7';

const recorder = recordSpans();

describe('remoteParent', () => {
  it('받은 traceparent 의 span 을 부모로 둔다. flags 00 이어도 남긴다', () => {
    tracer()
      .startSpan('child', {}, remoteParent(`00-${TRACE_ID}-${PARENT_ID}-00`))
      .end();

    const span = recorder.only('child');
    expect(traceIdOf(span)).toBe(TRACE_ID);
    expect(parentIdOf(span)).toBe(PARENT_ID);
    expect(span.parentSpanContext?.isRemote).toBe(true);
  });

  it.each([undefined, 'garbage', `01-${TRACE_ID}-${PARENT_ID}-01`])(
    '형식에 맞지 않는 %j 는 새 추적으로 시작한다',
    (header) => {
      tracer().startSpan('root', {}, remoteParent(header)).end();

      const span = recorder.only('root');
      expect(span.parentSpanContext).toBeUndefined();
      expect(traceIdOf(span)).not.toBe(TRACE_ID);
    },
  );
});

describe('지금의 span 을 읽는 것', () => {
  it('span 밖에서는 기록하지 않고, 추적도 traceparent 도 없다', () => {
    expect(isRecording()).toBe(false);
    expect(spanTrace()).toBeUndefined();
    expect(spanTraceparent()).toBeUndefined();
  });

  it('span 안에서는 그 span 의 추적과 traceparent 를 읽는다', () => {
    tracer().startActiveSpan('outer', (span) => {
      expect(isRecording()).toBe(true);
      expect(spanTrace()).toEqual({
        traceId: traceIdOf(span),
        flags: '01',
      });
      expect(spanTraceparent()).toBe(
        `00-${traceIdOf(span)}-${spanIdOf(span)}-01`,
      );
      span.end();
    });
  });

  it('받은 traceparent 만 걸린 곳(기록하지 않는 span)에서는 읽지 않는다', () => {
    context.with(remoteParent(`00-${TRACE_ID}-${PARENT_ID}-01`), () => {
      expect(isRecording()).toBe(false);
      expect(spanTrace()).toBeUndefined();
      expect(spanTraceparent()).toBeUndefined();
    });
  });

  it('지금의 span 에 속성을 싣는다. span 이 없으면 아무것도 하지 않는다', () => {
    tagCurrentSpan('request_id', 'outside');
    tracer().startActiveSpan('tagged', (span) => {
      tagCurrentSpan('request_id', 'req-1');
      recordHandled(3);
      span.end();
    });

    expect(recorder.only('tagged').attributes).toEqual({
      request_id: 'req-1',
      handled: 3,
    });
  });
});

describe('inJobSpan', () => {
  it('작업 한 바퀴를 새 추적의 span 으로 남긴다', async () => {
    const result = await inJobSpan('notification.send', 'job-1', () =>
      Promise.resolve(7),
    );

    expect(result).toBe(7);
    const span = recorder.only('notification.send');
    expect(span.parentSpanContext).toBeUndefined();
    expect(span.attributes).toEqual({
      [ATTRIBUTE_JOB_ID]: 'job-1',
      [ATTRIBUTE_RESULT]: 'success',
    });
    expect(span.status.code).toBe(SpanStatusCode.UNSET);
  });

  it('걸린 span 이 있으면 그 아래에 놓인다', async () => {
    await tracer().startActiveSpan('request', async (outer) => {
      await inJobSpan('notification.send', 'job-2', () => Promise.resolve());
      outer.end();
    });

    expect(parentIdOf(recorder.only('notification.send'))).toBe(
      spanIdOf(recorder.only('request')),
    );
  });

  it('실패하면 오류로 표시하고 예외를 그대로 올린다. 예외의 글은 싣지 않는다', async () => {
    const failure = new Error('postgresql://board:secret@db/trpg');

    await expect(
      inJobSpan('notification.send', 'job-3', () => Promise.reject(failure)),
    ).rejects.toBe(failure);

    const span = recorder.only('notification.send');
    expect(span.attributes[ATTRIBUTE_RESULT]).toBe('server_error');
    expect(span.status).toEqual({
      code: SpanStatusCode.ERROR,
      message: JOB_FAILED_ERROR_CODE,
    });
    expect(span.events).toEqual([]);
  });
});
