// board-server/src/write-limits/write-limits.policy.ts

/**
 * 글과 댓글을 얼마나 자주 쓸 수 있는가, 신고를 얼마나 자주 할 수 있는가. DB 도 Nest 도 모르는 순수한 값과 함수들이다.
 *
 * 도배를 막는 것이 목적이다. 사람이 쓰는 속도로는 닿기 어렵고, 프로그램으로 쏟아붓는 것은 금방 걸리는 선으로 잡았다.
 * 숫자를 설정(환경 변수)으로 빼지 않았다. 바꿀 일이 드물고, 잘못 넣으면 제한이 꺼지거나 아무도 쓰지 못한다.
 *
 * 운영자는 걸리지 않는다. 공지를 연달아 올려야 할 때가 있다.
 */

/** 정해 둔 시간 안에 쓸 수 있는 수. */
export interface WriteLimit {
  /** 이 시간(초) 동안 */
  windowSeconds: number;
  /** 이만큼까지 쓴다 */
  max: number;
}

/** 글: 10분에 5개 */
export const POST_LIMIT: WriteLimit = { windowSeconds: 10 * 60, max: 5 };
/** 댓글과 답글: 1분에 10개 */
export const COMMENT_LIMIT: WriteLimit = { windowSeconds: 60, max: 10 };
/** 신고: 1시간에 20건. 한 사람이 신고로 운영자의 목록을 덮지 못하게 한다 */
export const REPORT_LIMIT: WriteLimit = { windowSeconds: 60 * 60, max: 20 };

/** 쓰는 것마다의 한도. */
export interface WriteLimits {
  post: WriteLimit;
  comment: WriteLimit;
  report: WriteLimit;
}

/** 서버가 쓰는 한도 */
export const WRITE_LIMITS: WriteLimits = {
  post: POST_LIMIT,
  comment: COMMENT_LIMIT,
  report: REPORT_LIMIT,
};

/**
 * 한도에 걸렸을 때 기다릴 시간(초)을 다듬는다. 올림한 1 이상의 정수다.
 *
 * DB 가 셈한 값을 받는다. 가장 오래된 글이 창을 벗어날 때까지 남은 시간이다.
 * 0 이하나 숫자가 아닌 값이 오면 1 이다. "0초 뒤에 다시"는 지금 바로 다시 보내라는 말이 된다.
 */
export function retryAfterSeconds(remaining: unknown): number {
  const seconds = Math.ceil(Number(remaining));
  return Number.isFinite(seconds) && seconds >= 1 ? seconds : 1;
}
