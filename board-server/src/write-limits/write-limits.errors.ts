// board-server/src/write-limits/write-limits.errors.ts

/**
 * 쓰기 횟수 제한에 걸렸을 때의 응답들. 429 다. 기다릴 시간(초)을 retry_after 에 싣는다.
 * 응답의 Retry-After 머리말은 예외를 응답으로 바꾸는 곳이 retry_after 를 보고 붙인다(errors/all-exceptions.filter.ts).
 */

import { HttpException, HttpStatus } from '@nestjs/common';

/** 글을 너무 자주 썼다. */
export function tooManyPosts(retryAfter: number): HttpException {
  return new HttpException(
    {
      detail: '글을 너무 자주 쓰고 있습니다. 잠시 후 다시 시도해 주세요.',
      retry_after: retryAfter,
    },
    HttpStatus.TOO_MANY_REQUESTS,
  );
}

/** 댓글을 너무 자주 썼다. */
export function tooManyComments(retryAfter: number): HttpException {
  return new HttpException(
    {
      detail: '댓글을 너무 자주 쓰고 있습니다. 잠시 후 다시 시도해 주세요.',
      retry_after: retryAfter,
    },
    HttpStatus.TOO_MANY_REQUESTS,
  );
}
