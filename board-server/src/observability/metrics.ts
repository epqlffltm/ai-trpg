// board-server/src/observability/metrics.ts

/**
 * 메트릭의 계측기와, 그것을 OTLP(HTTP)로 수집기(Alloy)에 미는 것. 서버가 뜰 때 한 번 건다(main.ts).
 * 이름과 label 은 저장소 루트의 docs/observability.md 의 "메트릭"에 있다.
 * 알림 서버(notification-server/app/observability/metrics.py)와 같은 모양이다. 결제 서버(internal/metrics)가 본보기다.
 *
 * 계측기는 한 묶음(Instruments)으로 이 모듈에 둔다. 세는 곳은 record* 나 measuredJob 을 부른다.
 * MeterProvider 는 OpenTelemetry 의 전역에 두지 않는다. 전역은 프로세스에 한 번만 바꿀 수 있어
 * 테스트가 바꿔 끼우지 못한다. 처음에는 아무것도 하지 않는 것(noop)이다. 보낼 곳이 없으면 세기만 하고 보내지 않는다.
 *
 * 모은 값은 15초(OTEL_METRIC_EXPORT_INTERVAL)마다 타이머가 보낸다. 요청은 보내기를 기다리지 않는다.
 * 앱이 닫힐 때 남은 것을 한 번 보낸다(shutdownMetrics, observability.module.ts).
 * 수집기가 죽어 있어도 서버는 뜨고 요청은 영향을 받지 않는다. 보내지 못한 묶음은 버린다.
 */

import {
  Counter,
  createNoopMeter,
  Gauge,
  Histogram,
  Meter,
  ObservableResult,
  UpDownCounter,
} from '@opentelemetry/api';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-proto';
import { Resource } from '@opentelemetry/resources';
import {
  MeterProvider,
  PeriodicExportingMetricReader,
} from '@opentelemetry/sdk-metrics';
import { SERVICE_NAME } from './logger.factory.js';

/** OTLP(HTTP)로 메트릭을 받는 주소의 끝. 보내는 주소 뒤에 붙인다 */
export const METRICS_PATH = '/v1/metrics';
/** 수집기의 답을 기다리는 가장 긴 시간(밀리초). 닫을 때 남은 것을 보내는 것도 이만큼에서 포기한다 */
export const EXPORT_TIMEOUT_MS = 5000;
/**
 * 시간을 재는 히스토그램의 구간(초). SDK 의 기본 구간은 밀리초를 가정한 숫자라 초로 재면 거의 모두 첫 칸에 든다.
 * 다섯 서버가 같은 구간을 쓴다(docs/observability.md 의 "계측기를 만드는 법")
 */
export const DURATION_BUCKETS = [
  0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10,
];
/** 메서드 label 로 받는 것. 그 밖은 _OTHER 다. 받은 글자를 그대로 label 로 쓰면 시계열이 끝없이 는다 */
export const KNOWN_METHODS: ReadonlySet<string> = new Set([
  'GET',
  'HEAD',
  'POST',
  'PUT',
  'PATCH',
  'DELETE',
  'OPTIONS',
  'CONNECT',
  'TRACE',
]);
export const OTHER_METHOD = '_OTHER';
/** 작업이 끝난 모양. 로그의 result 와 같다 */
export const JOB_SUCCESS = 'success';
export const JOB_FAILED = 'server_error';

/** 글과 댓글을 쓴 것, 신고한 것의 결과(board_writes_total, board_reports_total 의 result) */
export type WriteResult = 'success' | 'rejected' | 'rate_limited';
/** 검색의 결과(board_searches_total 의 result) */
export type SearchResult = 'success' | 'timeout';

/** 연결 풀의 지금 값을 읽는 것. 쉬는 연결, 쓰는 연결, 가질 수 있는 가장 많은 연결. */
export interface PoolStats {
  idle: () => number;
  inUse: () => number;
  maximum: number;
}

/** 이 서버의 계측기 묶음. 이름에서 _total 과 단위를 뗀 것이다. Alloy 가 붙여 표의 이름이 된다. */
export interface Instruments {
  httpRequests: Counter;
  httpRequestDuration: Histogram;
  httpActiveRequests: UpDownCounter;
  dbUp: Gauge;
  dbPoolWait: Histogram;
  jobsStarted: Counter;
  jobsFinished: Counter;
  jobsRunning: UpDownCounter;
  jobDuration: Histogram;
  writes: Counter;
  searches: Counter;
  searchDuration: Histogram;
  reports: Counter;
}

/** 지금 지켜보는 연결 풀. 앱이 뜰 때 하나를 건다(watchPool). 앱에 하나다 */
let watchedPool: PoolStats | undefined;

/** 연결 풀의 값을 메트릭으로 내보내기 시작한다. 앞에 건 것을 바꾼다. */
export function watchPool(stats: PoolStats | undefined): void {
  watchedPool = stats;
}

/** db_pool_connections 의 값. 수집할 때마다 SDK 가 부른다. 지켜보는 풀이 없으면 아무것도 없다. */
export function observePoolConnections(result: ObservableResult): void {
  const pool = watchedPool;
  if (pool === undefined) {
    return;
  }
  result.observe(pool.idle(), { state: 'idle' });
  result.observe(pool.inUse(), { state: 'in_use' });
}

/** db_pool_connections_max 의 값. */
export function observePoolMaximum(result: ObservableResult): void {
  const pool = watchedPool;
  if (pool !== undefined) {
    result.observe(pool.maximum);
  }
}

/** 초로 재는 히스토그램. 구간은 DURATION_BUCKETS 다. */
export function durationHistogram(
  meter: Meter,
  name: string,
  description: string,
): Histogram {
  return meter.createHistogram(name, {
    unit: 's',
    description,
    advice: { explicitBucketBoundaries: DURATION_BUCKETS },
  });
}

/** meter 로 계측기를 만든다. 연결 풀의 값은 수집할 때 읽는 gauge 로 건다. */
export function buildInstruments(meter: Meter): Instruments {
  meter
    .createObservableGauge('db_pool_connections', {
      description: '연결 풀의 연결 수',
    })
    .addCallback(observePoolConnections);
  meter
    .createObservableGauge('db_pool_connections_max', {
      description: '풀이 가질 수 있는 가장 많은 연결',
    })
    .addCallback(observePoolMaximum);
  return {
    httpRequests: meter.createCounter('http_server_requests', {
      description: '끝난 요청의 수',
    }),
    httpRequestDuration: durationHistogram(
      meter,
      'http_server_request_duration',
      '요청을 받아 응답을 끝낼 때까지',
    ),
    httpActiveRequests: meter.createUpDownCounter(
      'http_server_active_requests',
      { description: '지금 처리 중인 요청의 수' },
    ),
    dbUp: meter.createGauge('db_up', {
      description: '준비 상태 확인이 마지막으로 본 DB 의 상태. 1 이면 닿는다',
    }),
    dbPoolWait: durationHistogram(
      meter,
      'db_pool_wait',
      '연결을 얻으려고 기다린 시간',
    ),
    jobsStarted: meter.createCounter('background_jobs_started', {
      description: '시작한 작업의 수',
    }),
    jobsFinished: meter.createCounter('background_jobs_finished', {
      description: '끝난 작업의 수',
    }),
    jobsRunning: meter.createUpDownCounter('background_jobs_running', {
      description: '지금 도는 작업의 수',
    }),
    jobDuration: durationHistogram(
      meter,
      'background_job_duration',
      '작업 하나가 걸린 시간',
    ),
    writes: meter.createCounter('board_writes', {
      description: '글과 댓글을 쓴 수',
    }),
    searches: meter.createCounter('board_searches', {
      description: '글을 검색한 수',
    }),
    searchDuration: durationHistogram(
      meter,
      'board_search_duration',
      '검색 하나가 걸린 시간',
    ),
    reports: meter.createCounter('board_reports', {
      description: '글과 댓글을 신고한 수',
    }),
  };
}

let measured: Instruments = buildInstruments(createNoopMeter());

/** 메트릭을 모으는 것을 바꿔 끼우고 계측기를 그것으로 다시 만든다. 서버가 뜰 때와 테스트가 부른다. */
export function useMeter(meter: Meter): void {
  measured = buildInstruments(meter);
}

/** 아무것도 하지 않는 것으로 되돌린다. 테스트가 끝날 때 부른다. */
export function useNoopMeter(): void {
  useMeter(createNoopMeter());
}

/** 지금 끼운 것의 계측기. */
export function instruments(): Instruments {
  return measured;
}

/** started(performance.now 의 값)부터 지금까지 걸린 시간(초). */
export function secondsSince(started: number): number {
  return (performance.now() - started) / 1000;
}

// --- HTTP 와 DB ---

/** 메서드 label. 정한 것이 아니면 _OTHER 다. */
export function methodLabel(method: string): string {
  return KNOWN_METHODS.has(method) ? method : OTHER_METHOD;
}

/** 끝난 요청 하나를 센다. route 는 경로의 틀이다(실제 주소가 아니다). */
export function recordRequest(
  method: string,
  route: string,
  statusCode: number,
  seconds: number,
): void {
  const labels = { method: methodLabel(method), route };
  measured.httpRequests.add(1, { ...labels, status_code: statusCode });
  measured.httpRequestDuration.record(seconds, labels);
}

/** 준비 상태 확인이 본 DB 의 상태를 적는다. */
export function recordDbUp(reachable: boolean): void {
  measured.dbUp.record(reachable ? 1 : 0);
}

/** 연결 하나를 얻으려고 기다린 시간을 적는다. */
export function recordPoolWait(seconds: number): void {
  measured.dbPoolWait.record(seconds);
}

// --- 작업 ---

/**
 * 작업 하나(도는 작업의 한 바퀴)를 센다. 시작, 도는 수, 걸린 시간, 끝난 모양(result)이다.
 *
 * 예외는 그대로 올린다. Node 에는 끄느라 멈춘 작업(취소)이 없다. 닫을 때는 도는 바퀴를 기다린다.
 */
export async function measuredJob<Result>(
  operation: string,
  work: () => Promise<Result>,
): Promise<Result> {
  const labels = { operation };
  const counting = measured;
  counting.jobsStarted.add(1, labels);
  counting.jobsRunning.add(1, labels);
  const started = performance.now();
  let result = JOB_FAILED;
  try {
    const done = await work();
    result = JOB_SUCCESS;
    return done;
  } finally {
    counting.jobsRunning.add(-1, labels);
    counting.jobDuration.record(secondsSince(started), labels);
    counting.jobsFinished.add(1, { ...labels, result });
  }
}

// --- 게시판 ---

/** 글이나 댓글을 쓴 것 하나를 센다. resource 는 post, comment, action 은 create, update, delete 다. */
export function recordWrite(
  resource: 'post' | 'comment',
  action: 'create' | 'update' | 'delete',
  result: WriteResult,
): void {
  measured.writes.add(1, { resource, action, result });
}

/** 검색 하나를 센다. 걸린 시간도 적는다. */
export function recordSearch(result: SearchResult, seconds: number): void {
  measured.searches.add(1, { result });
  measured.searchDuration.record(seconds);
}

/** 신고 하나를 센다. target 은 post, comment 다. */
export function recordReport(
  target: 'post' | 'comment',
  result: WriteResult,
): void {
  measured.reports.add(1, { target, result });
}

// --- 보내기 ---

/** 서버가 뜰 때 만든 것. 닫을 때 남은 것을 보내고 끈다 */
let configured: MeterProvider | undefined;

/**
 * 메트릭을 보내는 MeterProvider 를 만든다. 보낼 곳이 없으면 undefined 다. 만드는 것만으로는 수집기에 닿지 않는다.
 *
 * intervalMs 는 보내는 간격(밀리초)이다(OTEL_METRIC_EXPORT_INTERVAL).
 * 답을 기다리는 시간은 간격보다 길 수 없다(SDK 가 만들지 않고 예외를 낸다). 간격이 5초보다 짧으면 간격만큼 기다린다.
 */
export function buildMeterProvider(
  endpoint: string,
  intervalMs: number,
  resource: Resource,
): MeterProvider | undefined {
  if (endpoint === '') {
    return undefined;
  }
  const exporter = new OTLPMetricExporter({
    url: endpoint + METRICS_PATH,
    timeoutMillis: EXPORT_TIMEOUT_MS,
  });
  const reader = new PeriodicExportingMetricReader({
    exporter,
    exportIntervalMillis: intervalMs,
    exportTimeoutMillis: Math.min(EXPORT_TIMEOUT_MS, intervalMs),
  });
  return new MeterProvider({ resource, readers: [reader] });
}

/**
 * 보낼 곳이 있으면 메트릭을 보내는 것을 만들어 끼운다. 만든 것을 돌려준다. 없으면 undefined 다.
 *
 * 보낼 곳이 없으면 끼워 둔 것을 건드리지 않는다. 테스트가 끼운 것(메모리에 모으는 것)이 그대로 남는다.
 */
export function configureMetrics(
  endpoint: string,
  intervalMs: number,
  resource: Resource,
): MeterProvider | undefined {
  const provider = buildMeterProvider(endpoint, intervalMs, resource);
  if (provider !== undefined) {
    useMeter(provider.getMeter(SERVICE_NAME));
    configured = provider;
  }
  return provider;
}

/** configureMetrics 가 만든 것이 모아 둔 값을 한 번 보내고 끈다. 만든 것이 없으면 아무것도 하지 않는다. */
export async function shutdownMetrics(): Promise<void> {
  const provider = configured;
  configured = undefined;
  await provider?.shutdown({ timeoutMillis: EXPORT_TIMEOUT_MS });
}
