// board-server/src/database/database.health.spec.ts

/**
 * DB 에 닿는지 확인하는 것을 검증한다. DB 를 띄우지 않고 가짜 연결을 꽂는다.
 * 시간이 지나는 것은 가짜 시계로 만든다. 실제로 3초를 기다리지 않는다.
 */

import { DataSource } from 'typeorm';
import {
  DatabaseHealth,
  PING_TIMEOUT_MS,
  PingTimeoutError,
  withinTime,
} from './database.health.js';

/** query 가 정해 둔 대로 끝나는 가짜 연결. */
function makeHealth(query: () => Promise<unknown>): DatabaseHealth {
  return new DatabaseHealth({ query } as unknown as DataSource);
}

/** 끝나지 않는 일. 멈춘 DB 의 흉내다 */
function never(): Promise<never> {
  return new Promise<never>(() => undefined);
}

describe('DatabaseHealth', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('DB 가 답하면 끝난다', async () => {
    const health = makeHealth(() => Promise.resolve([{ '?column?': 1 }]));

    await expect(health.ping()).resolves.toBeUndefined();
  });

  it('DB 의 오류는 그대로 낸다', async () => {
    class ConnectionRefused extends Error {}
    const health = makeHealth(() =>
      Promise.reject(new ConnectionRefused('끊겼다')),
    );

    await expect(health.ping()).rejects.toBeInstanceOf(ConnectionRefused);
  });

  it('정해 둔 시간 안에 답이 없으면 시간 초과로 끝난다', async () => {
    const health = makeHealth(never);

    const pinged = health.ping();
    const checked = expect(pinged).rejects.toBeInstanceOf(PingTimeoutError);
    await vi.advanceTimersByTimeAsync(PING_TIMEOUT_MS);

    await checked;
  });

  it('시간이 되기 전에는 끝나지 않는다', async () => {
    const health = makeHealth(never);
    let settled = false;

    health
      .ping()
      .catch(() => undefined)
      .finally(() => (settled = true));
    await vi.advanceTimersByTimeAsync(PING_TIMEOUT_MS - 1);

    expect(settled).toBe(false);
  });

  it('compose 의 healthcheck 가 기다리는 5초보다 짧다', () => {
    // 길면 확인하는 쪽이 먼저 포기해서 503 이 닿지 않는다
    expect(PING_TIMEOUT_MS).toBeLessThan(5000);
  });
});

describe('withinTime', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('제때 끝나면 타이머를 남기지 않는다', async () => {
    await withinTime(Promise.resolve('끝'), 1000);

    expect(vi.getTimerCount()).toBe(0);
  });

  it('늦게 끝난 일의 오류는 버린다', async () => {
    let fail: (error: Error) => void = () => undefined;
    const late = new Promise<never>((_, reject) => (fail = reject));

    const result = withinTime(late, 1000);
    const checked = expect(result).rejects.toBeInstanceOf(PingTimeoutError);
    await vi.advanceTimersByTimeAsync(1000);
    await checked;

    // 시간이 지난 뒤에 거부되어도 처리되지 않은 거부가 되지 않는다(되면 vitest 가 실패로 센다)
    fail(new Error('늦은 오류'));
    await vi.runAllTimersAsync();
  });
});
