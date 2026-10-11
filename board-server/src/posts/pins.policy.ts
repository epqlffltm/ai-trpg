// board-server/src/posts/pins.policy.ts

/**
 * 글 고정에 관한 규칙. DB 도 Nest 도 모르는 순수한 함수들이다.
 *
 *   - 고정하고 푸는 것은 운영자만 한다. 글쓴이도 제 글을 고정하지 못한다.
 *   - 고정에는 끝이 있다. 고정할 때 며칠 동안인지 정하고, 그날이 지나면 저절로 내려간다.
 *     "저절로"는 읽을 때 정해진다. 끝나는 시각이 지난 글을 고정한 글로 읽지 않을 뿐이다.
 *     시각이 지난 행을 찾아 열을 비우는 작업을 따로 돌리지 않는다. 그 작업이 멈춰도 공지가 남지 않는다.
 *   - 한 게시판에 고정할 수 있는 글의 수에 끝이 있다. 없으면 목록의 첫 쪽이 고정한 글로 덮인다.
 */

import { Post } from './post.entity.js';

/** 한 게시판에 함께 고정해 둘 수 있는 글의 수 */
export const MAX_PINS_PER_BOARD = 5;
/** 며칠 동안인지 적지 않았을 때의 고정 기간(일) */
export const DEFAULT_PIN_DAYS = 7;
/** 가장 긴 고정 기간(일) */
export const MAX_PIN_DAYS = 365;

const MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000;

/** 고정에 관해 글에서 보는 칸. */
export type Pinnable = Pick<Post, 'pinnedUntil'>;

/** 지금 고정하면 언제 끝나는가. */
export function pinEndsAt(now: Date, days: number): Date {
  return new Date(now.getTime() + days * MILLISECONDS_PER_DAY);
}

/** 이 글은 지금 고정되어 있는가. 끝나는 시각이 지났으면 아니다. */
export function isPinned(post: Pinnable, now: Date): boolean {
  return post.pinnedUntil !== null && post.pinnedUntil > now;
}

/** 고정이 끝나는 시각. 지금 고정되어 있지 않으면 null 이다. 지난 시각은 내보내지 않는다. */
export function pinnedUntilOf(post: Pinnable, now: Date): Date | null {
  return isPinned(post, now) ? post.pinnedUntil : null;
}

/** 이 사람이 글을 고정하거나 풀어도 되는가. 운영자만이다. */
export function canPin(isOperator: boolean): boolean {
  return isOperator;
}

/** 이 게시판에 글을 하나 더 고정해도 되는가. othersPinned 는 이 글 말고 지금 고정되어 있는 글의 수다. */
export function hasRoomToPin(othersPinned: number): boolean {
  return othersPinned < MAX_PINS_PER_BOARD;
}
