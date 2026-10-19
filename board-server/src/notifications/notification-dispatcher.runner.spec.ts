// board-server/src/notifications/notification-dispatcher.runner.spec.ts

/**
 * 보내는 작업을 돌리는 것(notification-dispatcher.runner.ts)을 검증한다. 진짜 보내는 작업 대신 가짜를 꽂는다.
 */

import { Logger } from '@nestjs/common';
import { SpanStatusCode } from '@opentelemetry/api';
import { recordSpans } from '../../test/spans.js';
import {
  Dispatched,
  NotificationDispatcher,
} from './notification-dispatcher.js';
import {
  handledOf,
  NotificationDispatchRunner,
} from './notification-dispatcher.runner.js';

const recorder = recordSpans();

/** 한 바퀴의 결과. 넘긴 것만 채우고 나머지는 0 이다. */
function dispatched(counts: Partial<Dispatched> = {}): Dispatched {
  return { sent: 0, retried: 0, rejected: 0, failed: 0, dropped: 0, ...counts };
}

describe('handledOf', () => {
  it('보낸 것, 다시 보낼 것, 받지 않은 것, 예외, 지운 것을 모두 센다', () => {
    expect(handledOf(dispatched())).toBe(0);
    expect(
      handledOf(
        dispatched({ sent: 1, retried: 2, rejected: 3, failed: 4, dropped: 5 }),
      ),
    ).toBe(15);
  });
});

/** tick 이 끝나지 않게 붙잡아 둘 수 있는 가짜. */
function fakeDispatcher(tick: () => Promise<unknown>): NotificationDispatcher {
  return { tick } as unknown as NotificationDispatcher;
}

describe('NotificationDispatchRunner', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('앞 바퀴가 끝나지 않았으면 다음 바퀴를 건너뛴다', async () => {
    let release: () => void = () => undefined;
    const tick = vi
      .fn<() => Promise<Dispatched>>()
      .mockImplementationOnce(
        () =>
          new Promise<Dispatched>(
            (resolve) => (release = () => resolve(dispatched())),
          ),
      )
      .mockResolvedValue(dispatched());
    const runner = new NotificationDispatchRunner(fakeDispatcher(tick));

    const first = runner.runOnce();
    await runner.runOnce();
    release();
    await first;
    await runner.runOnce();

    expect(tick).toHaveBeenCalledTimes(2);
  });

  it('바퀴가 통째로 실패해도 오류로 남기고 다음 바퀴를 돈다', async () => {
    const error = vi
      .spyOn(Logger.prototype, 'error')
      .mockImplementation(() => undefined);
    const tick = vi
      .fn()
      .mockRejectedValueOnce(new Error('DB 가 없다'))
      .mockResolvedValueOnce(dispatched());
    const runner = new NotificationDispatchRunner(fakeDispatcher(tick));

    await runner.runOnce();
    await runner.runOnce();

    expect(tick).toHaveBeenCalledTimes(2);
    expect(error).toHaveBeenCalledWith(
      expect.objectContaining({
        error_code: 'job.failed',
        error_type: 'Error',
      }),
      expect.any(String),
    );
  });

  it('바퀴마다 작업의 span 을 걸고 처리한 수를 싣는다. 할 일이 없던 바퀴는 남기지 않는다', async () => {
    const tick = vi
      .fn()
      .mockResolvedValueOnce(dispatched())
      .mockResolvedValueOnce(dispatched({ sent: 2 }));
    const runner = new NotificationDispatchRunner(fakeDispatcher(tick));

    await runner.runOnce();
    await runner.runOnce();

    const job = recorder.only('notification.send');
    expect(job.attributes).toMatchObject({ handled: 2, result: 'success' });
    expect(job.parentSpanContext).toBeUndefined();
  });

  it('통째로 실패한 바퀴는 실패로 남는다', async () => {
    vi.spyOn(Logger.prototype, 'error').mockImplementation(() => undefined);
    const runner = new NotificationDispatchRunner(
      fakeDispatcher(() => Promise.reject(new Error('DB 가 없다'))),
    );

    await runner.runOnce();

    expect(recorder.only('notification.send').status.code).toBe(
      SpanStatusCode.ERROR,
    );
  });

  it('뜨면 타이머를 걸고, 닫히면 멈춘다', () => {
    const runner = new NotificationDispatchRunner(
      fakeDispatcher(() => Promise.resolve()),
    );

    runner.onApplicationBootstrap();
    runner.onModuleDestroy();

    expect(() => runner.onModuleDestroy()).not.toThrow();
  });
});
