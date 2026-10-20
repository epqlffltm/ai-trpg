// board-server/src/observability/metrics.spec.ts

/**
 * 메트릭의 계측기와 보내는 것(metrics.ts)을 검증한다. 이름, 단위, label 이 docs/observability.md 의 "메트릭"의 표와 같은지 본다.
 * 세는 것은 메모리에 모으는 것(test/metrics.ts)으로 읽고, 보내는 것은 이 컴퓨터 안의 가짜 수집기(test/collector.ts)로 본다.
 */

import { Collector } from '../../test/collector.js';
import { recordMetrics } from '../../test/metrics.js';
import {
  buildMeterProvider,
  configureMetrics,
  DURATION_BUCKETS,
  measuredJob,
  methodLabel,
  METRICS_PATH,
  OTHER_METHOD,
  recordDbUp,
  recordPoolWait,
  recordReport,
  recordRequest,
  recordSearch,
  recordWrite,
  shutdownMetrics,
  useNoopMeter,
  watchPool,
} from './metrics.js';
import { buildResource } from './tracing.js';

const INFO = { service: 'board-server', environment: 'test', version: '1.2.3' };
const metrics = recordMetrics();

afterEach(() => watchPool(undefined));

describe('HTTP 와 DB', () => {
  it('끝난 요청을 메서드, 경로의 틀, 상태 코드로 센다. 시간은 초다', async () => {
    recordRequest('GET', '/api/v1/board/posts/:id', 200, 0.02);

    const labels = { method: 'GET', route: '/api/v1/board/posts/:id' };
    expect(
      await metrics.current.value('http_server_requests', {
        ...labels,
        status_code: 200,
      }),
    ).toBe(1);
    const [duration] = await metrics.current.points(
      'http_server_request_duration',
    );
    expect(duration).toMatchObject({ labels, unit: 's', value: 1 });
    expect(duration.boundaries).toEqual(DURATION_BUCKETS);
  });

  it('정하지 않은 메서드는 _OTHER 하나로 센다', () => {
    expect(methodLabel('GET')).toBe('GET');
    expect(methodLabel('BREW')).toBe(OTHER_METHOD);
  });

  it('DB 에 닿았는지를 1 과 0 으로 적는다', async () => {
    recordDbUp(true);
    expect(await metrics.current.value('db_up')).toBe(1);

    recordDbUp(false);
    expect(await metrics.current.value('db_up')).toBe(0);
  });

  it('지켜보는 풀의 연결 수를 수집할 때 읽는다. 없으면 내지 않는다', async () => {
    expect(await metrics.current.points('db_pool_connections')).toEqual([]);

    watchPool({ idle: () => 3, inUse: () => 2, maximum: 10 });

    expect(
      await metrics.current.value('db_pool_connections', { state: 'idle' }),
    ).toBe(3);
    expect(
      await metrics.current.value('db_pool_connections', { state: 'in_use' }),
    ).toBe(2);
    expect(await metrics.current.value('db_pool_connections_max')).toBe(10);
  });

  it('연결을 기다린 시간을 초로 적는다', async () => {
    recordPoolWait(0.004);

    const [wait] = await metrics.current.points('db_pool_wait');
    expect(wait).toMatchObject({ unit: 's', value: 1 });
  });
});

describe('작업', () => {
  it('끝난 작업을 시작, 도는 수, 걸린 시간, 결과로 센다', async () => {
    let running: number | undefined;

    const result = await measuredJob('notification.send', async () => {
      running = await metrics.current.value('background_jobs_running', {
        operation: 'notification.send',
      });
      return 7;
    });

    const labels = { operation: 'notification.send' };
    expect(result).toBe(7);
    expect(running).toBe(1);
    expect(await metrics.current.value('background_jobs_started', labels)).toBe(
      1,
    );
    expect(
      await metrics.current.value('background_jobs_finished', {
        ...labels,
        result: 'success',
      }),
    ).toBe(1);
    expect(await metrics.current.value('background_jobs_running', labels)).toBe(
      0,
    );
    expect(await metrics.current.value('background_job_duration', labels)).toBe(
      1,
    );
  });

  it('실패한 작업은 server_error 로 세고 예외를 그대로 올린다', async () => {
    await expect(
      measuredJob('notification.send', () =>
        Promise.reject(new Error('부서졌다')),
      ),
    ).rejects.toThrow('부서졌다');

    expect(
      await metrics.current.value('background_jobs_finished', {
        operation: 'notification.send',
        result: 'server_error',
      }),
    ).toBe(1);
  });
});

describe('게시판', () => {
  it('쓰기, 검색, 신고를 표의 label 로 센다', async () => {
    recordWrite('post', 'create', 'success');
    recordWrite('comment', 'delete', 'rejected');
    recordSearch('timeout', 3.1);
    recordReport('comment', 'rate_limited');

    expect(
      await metrics.current.value('board_writes', {
        resource: 'post',
        action: 'create',
        result: 'success',
      }),
    ).toBe(1);
    expect(
      await metrics.current.value('board_writes', {
        resource: 'comment',
        action: 'delete',
        result: 'rejected',
      }),
    ).toBe(1);
    expect(
      await metrics.current.value('board_searches', { result: 'timeout' }),
    ).toBe(1);
    const [duration] = await metrics.current.points('board_search_duration');
    expect(duration).toMatchObject({ unit: 's', value: 1 });
    expect(
      await metrics.current.value('board_reports', {
        target: 'comment',
        result: 'rate_limited',
      }),
    ).toBe(1);
  });
});

describe('보내기', () => {
  it('보낼 곳이 없으면 만들지 않고, 끼워 둔 것을 건드리지 않는다', async () => {
    expect(buildMeterProvider('', 15000, buildResource(INFO))).toBeUndefined();
    expect(configureMetrics('', 15000, buildResource(INFO))).toBeUndefined();
    recordDbUp(true);

    expect(await metrics.current.value('db_up')).toBe(1);
  });

  it('보낼 곳이 있으면 /v1/metrics 로 protobuf 를 보낸다. 끌 때 남은 것을 보낸다', async () => {
    const collector = new Collector();
    const endpoint = await collector.start();
    try {
      expect(
        configureMetrics(endpoint, 60_000, buildResource(INFO)),
      ).toBeDefined();
      recordRequest('GET', '/health', 200, 0.01);

      await shutdownMetrics();

      expect(collector.received).toHaveLength(1);
      expect(collector.received[0]).toMatchObject({
        path: METRICS_PATH,
        contentType: 'application/x-protobuf',
      });
      expect(collector.received[0].bytes).toBeGreaterThan(0);
    } finally {
      useNoopMeter();
      await collector.stop();
    }
  });

  it('간격이 답을 기다리는 시간(5초)보다 짧아도 만든다', async () => {
    const provider = buildMeterProvider(
      'http://127.0.0.1:9',
      1000,
      buildResource(INFO),
    );

    expect(provider).toBeDefined();
    await provider?.shutdown({ timeoutMillis: 100 });
  });

  it('켠 것이 없으면 끄는 것은 아무것도 하지 않는다', async () => {
    await expect(shutdownMetrics()).resolves.toBeUndefined();
  });
});
