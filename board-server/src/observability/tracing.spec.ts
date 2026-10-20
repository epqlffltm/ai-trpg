// board-server/src/observability/tracing.spec.ts

/**
 * span 을 보내는 것(tracing.ts)을 검증한다. 이 컴퓨터 안에 가짜 수집기를 띄워 실제로 보내 본다.
 */

import { trace } from '@opentelemetry/api';
import {
  buildProvider,
  buildResource,
  configureTracing,
  instanceId,
  shutdownTracing,
  TRACES_PATH,
} from './tracing.js';
import { Collector } from '../../test/collector.js';
import { SpanRecorder } from '../../test/spans.js';
import { tracer, useProvider } from './spans.js';

const INFO = { service: 'board-server', environment: 'test', version: '1.2.3' };

describe('출처', () => {
  it('프로세스마다 다른 이름을 붙인다', () => {
    expect(instanceId('server')).toMatch(/^server-[0-9a-f]{8}$/);
    expect(instanceId('server')).not.toBe(instanceId('server'));
  });

  it('정한 넷만 싣는다. 환경 변수와 호스트의 정보는 싣지 않는다', () => {
    process.env.OTEL_RESOURCE_ATTRIBUTES = 'leak=yes';
    try {
      const resource = buildResource(INFO, 'server');

      expect(Object.keys(resource.attributes).sort()).toEqual([
        'deployment.environment.name',
        'service.instance.id',
        'service.name',
        'service.version',
      ]);
      expect(resource.attributes['service.name']).toBe('board-server');
      expect(resource.attributes['service.version']).toBe('1.2.3');
      expect(resource.attributes['deployment.environment.name']).toBe('test');
    } finally {
      delete process.env.OTEL_RESOURCE_ATTRIBUTES;
    }
  });
});

describe('buildProvider, configureTracing', () => {
  it('보낼 곳이 없으면 만들지 않고, 끼워 둔 것을 건드리지 않는다', async () => {
    const recorder = new SpanRecorder();
    recorder.start();
    try {
      expect(buildProvider('', buildResource(INFO))).toBeUndefined();
      expect(configureTracing('', buildResource(INFO))).toBeUndefined();
      tracer().startSpan('still-recorded').end();

      expect(recorder.named('still-recorded')).toHaveLength(1);
    } finally {
      await recorder.stop();
    }
  });

  it('보낼 곳이 있으면 /v1/traces 로 protobuf 를 보낸다. 끌 때 남은 것을 보낸다', async () => {
    const collector = new Collector();
    const endpoint = await collector.start();
    const previous = trace.getTracerProvider();
    try {
      expect(configureTracing(endpoint, buildResource(INFO))).toBeDefined();
      tracer().startSpan('GET /api/v1/board/boards').end();

      await shutdownTracing();

      expect(collector.received).toHaveLength(1);
      expect(collector.received[0]).toMatchObject({
        path: TRACES_PATH,
        contentType: 'application/x-protobuf',
      });
      expect(collector.received[0].bytes).toBeGreaterThan(0);
    } finally {
      useProvider(previous);
      await collector.stop();
    }
  });

  it('켠 것이 없으면 끄는 것은 아무것도 하지 않는다', async () => {
    await expect(shutdownTracing()).resolves.toBeUndefined();
  });
});
