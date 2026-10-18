// board-server/src/notifications/notification-dispatcher.spec.ts

/**
 * 보내는 작업의 셈(notification-dispatcher.ts)을 검증한다. DB 를 쓰는 바퀴는 test/notifications.e2e-spec.ts 가 본다.
 */

import {
  countDelivery,
  Dispatched,
  isBusy,
  retryDelayMs,
} from './notification-dispatcher.js';

const NOTHING: Dispatched = {
  sent: 0,
  retried: 0,
  rejected: 0,
  failed: 0,
  dropped: 0,
};

describe('retryDelayMs', () => {
  it.each([
    [0, 10_000],
    [1, 10_000],
    [2, 20_000],
    [3, 40_000],
    [9, 2_560_000],
    [10, 3_600_000],
    [30, 3_600_000],
  ])('%i 번째로 못 보낸 뒤에는 %i 밀리초를 기다린다', (attempts, expected) => {
    expect(retryDelayMs(attempts)).toBe(expected);
  });
});

describe('countDelivery', () => {
  it('결과마다 한 칸을 센다. 예외(null)는 failed 다', () => {
    const counted = [
      'delivered',
      'unavailable',
      'rejected',
      null,
      'delivered',
    ].reduce<Dispatched>(
      (sum, delivery) =>
        countDelivery(sum, delivery as Parameters<typeof countDelivery>[1]),
      NOTHING,
    );

    expect(counted).toEqual({
      sent: 2,
      retried: 1,
      rejected: 1,
      failed: 1,
      dropped: 0,
    });
  });
});

describe('isBusy', () => {
  it('한 일이 하나라도 있으면 참이다', () => {
    expect(isBusy(NOTHING)).toBe(false);
    expect(isBusy({ ...NOTHING, dropped: 1 })).toBe(true);
  });
});
