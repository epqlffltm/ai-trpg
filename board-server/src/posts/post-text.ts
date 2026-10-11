// board-server/src/posts/post-text.ts

/**
 * 글의 제목과 본문에 함께 쓰는 규칙.
 */

import { TransformFnParams } from 'class-transformer';

/** 빈칸이 아닌 글자가 하나는 있다. 빈칸만 적은 글을 막는다 */
export const HAS_VISIBLE_TEXT = /\S/;
/** NUL 글자가 없다. PostgreSQL 의 글자 칸은 NUL 을 담지 못해서, 받으면 저장할 때 오류가 난다 */
// oxlint-disable-next-line no-control-regex -- NUL 을 찾으려고 일부러 적은 것이다
export const NO_NUL = /^[^\u0000]*$/;

/** 글자면 앞뒤 빈칸을 뗀다. 글자가 아니면 그대로 둔다. 그것은 뒤의 검사가 거부한다. */
export function trimText({ value }: TransformFnParams): unknown {
  return typeof value === 'string' ? value.trim() : value;
}
