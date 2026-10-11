// board-server/src/posts/post-id.pipe.ts

/**
 * 주소의 글 번호(/posts/1234)를 검사한다.
 *
 * 글 번호는 1 이상의 정수다. 그 모양이 아니면 그런 글이 없는 것이므로 404 다. DB 에 묻지 않는다.
 * 번호는 글자 그대로 넘긴다. 숫자로 바꾸지 않는다. JavaScript 의 숫자는 큰 정수를 정확히 담지 못한다.
 */

import { Injectable, PipeTransform } from '@nestjs/common';
import { postNotFound } from './posts.errors.js';

/** 글 번호의 모양. 0 으로 시작하지 않는 숫자, 18자리까지. DB 의 bigint 에 들어가는 크기다 */
const POST_ID = /^[1-9]\d{0,17}$/;

/** 글자가 글 번호의 모양인가. */
export function isPostId(value: unknown): value is string {
  return typeof value === 'string' && POST_ID.test(value);
}

@Injectable()
export class PostIdPipe implements PipeTransform<unknown, string> {
  transform(value: unknown): string {
    if (!isPostId(value)) {
      throw postNotFound();
    }
    return value;
  }
}
