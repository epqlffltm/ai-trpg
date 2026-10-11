// board-server/src/posts/pins.policy.spec.ts

/**
 * 글 고정에 관한 규칙(pins.policy.ts)을 검증한다.
 */

import {
  canPin,
  hasRoomToPin,
  isPinned,
  MAX_PINS_PER_BOARD,
  pinEndsAt,
  pinnedUntilOf,
} from './pins.policy.js';

const NOW = new Date('2026-10-11T09:00:00.000Z');
const LATER = new Date('2026-10-11T09:00:00.001Z');
const EARLIER = new Date('2026-10-11T08:59:59.999Z');

describe('pinEndsAt', () => {
  it('며칠 뒤의 같은 시각이다', () => {
    expect(pinEndsAt(NOW, 7).toISOString()).toBe('2026-10-18T09:00:00.000Z');
    expect(pinEndsAt(NOW, 1).toISOString()).toBe('2026-10-12T09:00:00.000Z');
  });

  it('받은 시각을 바꾸지 않는다', () => {
    pinEndsAt(NOW, 30);

    expect(NOW.toISOString()).toBe('2026-10-11T09:00:00.000Z');
  });
});

describe('isPinned', () => {
  it('고정한 적이 없는 글은 고정된 글이 아니다', () => {
    expect(isPinned({ pinnedUntil: null }, NOW)).toBe(false);
  });

  it('끝나는 시각이 아직 오지 않았으면 고정된 글이다', () => {
    expect(isPinned({ pinnedUntil: LATER }, NOW)).toBe(true);
  });

  it('끝나는 시각이 지났으면 고정된 글이 아니다', () => {
    expect(isPinned({ pinnedUntil: EARLIER }, NOW)).toBe(false);
  });

  it('끝나는 바로 그 시각에는 이미 풀린 것이다', () => {
    expect(isPinned({ pinnedUntil: NOW }, NOW)).toBe(false);
  });
});

describe('pinnedUntilOf', () => {
  it('고정된 글이면 끝나는 시각이다', () => {
    expect(pinnedUntilOf({ pinnedUntil: LATER }, NOW)).toBe(LATER);
  });

  it('지난 시각은 내보내지 않는다', () => {
    // 열에는 남아 있어도, 밖에서 보기에는 고정하지 않은 글이다
    expect(pinnedUntilOf({ pinnedUntil: EARLIER }, NOW)).toBeNull();
    expect(pinnedUntilOf({ pinnedUntil: null }, NOW)).toBeNull();
  });
});

describe('canPin', () => {
  it('운영자만 고정한다', () => {
    expect(canPin(true)).toBe(true);
    expect(canPin(false)).toBe(false);
  });
});

describe('hasRoomToPin', () => {
  it('정해 둔 수까지만 고정한다', () => {
    expect(hasRoomToPin(0)).toBe(true);
    expect(hasRoomToPin(MAX_PINS_PER_BOARD - 1)).toBe(true);
    expect(hasRoomToPin(MAX_PINS_PER_BOARD)).toBe(false);
  });
});
