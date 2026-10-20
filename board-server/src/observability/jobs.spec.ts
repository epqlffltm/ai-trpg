// board-server/src/observability/jobs.spec.ts

/**
 * 작업 한 바퀴를 거는 것(jobs.ts)과 그 바퀴의 작업 메트릭, 작업과 span 이 걸렸을 때 로그의 식별자와 보내는 머리말(request-context.ts)을 검증한다.
 */

import { recordMetrics } from '../../test/metrics.js';
import { recordSpans, spanIdOf, traceIdOf } from '../../test/spans.js';
import { runAsJob } from './jobs.js';
import {
  currentIds,
  outgoingHeaders,
  runInRequest,
} from './request-context.js';
import { ATTRIBUTE_JOB_ID, tracer } from './spans.js';

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const TRACE = { traceId: '4bf92f3577b34da6a3ce929d0e0e4736', flags: '00' };

const recorder = recordSpans();
const metrics = recordMetrics();

describe('runAsJob', () => {
  it('바퀴마다 작업의 메트릭을 센다. 실패한 바퀴는 server_error 다', async () => {
    await runAsJob('notification.send', () => Promise.resolve());
    await expect(
      runAsJob('notification.send', () => Promise.reject(new Error('없다'))),
    ).rejects.toThrow('없다');

    const labels = { operation: 'notification.send' };
    expect(await metrics.current.value('background_jobs_started', labels)).toBe(
      2,
    );
    expect(
      await metrics.current.value('background_jobs_finished', {
        ...labels,
        result: 'success',
      }),
    ).toBe(1);
    expect(
      await metrics.current.value('background_jobs_finished', {
        ...labels,
        result: 'server_error',
      }),
    ).toBe(1);
  });

  it('바퀴 안의 로그에 job_id 와 그 span 의 trace_id 가 붙고 request_id 는 없다', async () => {
    const ids = await runAsJob('notification.send', () =>
      Promise.resolve(currentIds()),
    );

    const span = recorder.only('notification.send');
    expect(ids).toEqual({
      job_id: span.attributes[ATTRIBUTE_JOB_ID],
      trace_id: traceIdOf(span),
    });
    expect(ids.job_id).toMatch(UUID);
    expect(currentIds()).toEqual({});
  });

  it('바퀴마다 새 job_id 와 새 추적이다', async () => {
    const first = await runAsJob('notification.send', () =>
      Promise.resolve(currentIds()),
    );
    const second = await runAsJob('notification.send', () =>
      Promise.resolve(currentIds()),
    );

    expect(first.job_id).not.toBe(second.job_id);
    expect(first.trace_id).not.toBe(second.trace_id);
  });

  it('실패하면 예외를 그대로 올린다', async () => {
    await expect(
      runAsJob('notification.send', () => Promise.reject(new Error('없다'))),
    ).rejects.toThrow('없다');
  });
});

describe('outgoingHeaders', () => {
  it('걸린 것이 없으면 비어 있다', () => {
    expect(outgoingHeaders()).toEqual({});
  });

  it('span 이 없으면 걸린 요청의 추적을 잇는다(부모 번호는 새로 만든다)', () => {
    const headers = runInRequest({ requestId: 'req-1', trace: TRACE }, () =>
      outgoingHeaders(),
    );

    expect(headers.traceparent).toMatch(
      new RegExp(`^00-${TRACE.traceId}-[0-9a-f]{16}-00$`),
    );
  });

  it('기록 중인 span 이 있으면 그 span 을 가리킨다', () => {
    tracer().startActiveSpan('request', (span) => {
      expect(outgoingHeaders()).toEqual({
        traceparent: `00-${traceIdOf(span)}-${spanIdOf(span)}-01`,
      });
      span.end();
    });
  });
});
