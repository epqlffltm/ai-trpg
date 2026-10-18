// board-server/src/notifications/notification-dispatcher.runner.spec.ts

/**
 * 보내는 작업을 돌리는 것(notification-dispatcher.runner.ts)을 검증한다. 진짜 보내는 작업 대신 가짜를 꽂는다.
 */

import { Logger } from '@nestjs/common';
import { NotificationDispatcher } from './notification-dispatcher.js';
import { NotificationDispatchRunner } from './notification-dispatcher.runner.js';

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
      .fn<() => Promise<void>>()
      .mockImplementationOnce(
        () => new Promise<void>((resolve) => (release = resolve)),
      )
      .mockResolvedValue(undefined);
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
      .mockResolvedValueOnce(undefined);
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

  it('뜨면 타이머를 걸고, 닫히면 멈춘다', () => {
    const runner = new NotificationDispatchRunner(
      fakeDispatcher(() => Promise.resolve()),
    );

    runner.onApplicationBootstrap();
    runner.onModuleDestroy();

    expect(() => runner.onModuleDestroy()).not.toThrow();
  });
});
