// board-server/src/boards/board-slug.pipe.ts

/**
 * 주소의 게시판 이름(/boards/free/posts)을 검사한다.
 *
 * 게시판의 이름(slug)은 영문 소문자, 숫자, 붙임표로 된 30자까지의 글자다. 그 모양이 아니면
 * 그런 게시판이 없는 것이므로 404 다. DB 에 묻지 않는다. 주소로 들어온 NUL 글자 같은 것을
 * 그대로 DB 에 물으면 DB 가 오류를 낸다.
 */

import { Injectable, PipeTransform } from '@nestjs/common';
import { boardNotFound } from './boards.service.js';

/** 게시판 이름의 모양. boards 테이블의 slug 칸에 들어가는 길이다 */
export const BOARD_SLUG = /^[a-z0-9-]{1,30}$/;

/** 글자가 게시판 이름의 모양인가. */
export function isBoardSlug(value: unknown): value is string {
  return typeof value === 'string' && BOARD_SLUG.test(value);
}

@Injectable()
export class BoardSlugPipe implements PipeTransform<unknown, string> {
  transform(value: unknown): string {
    if (!isBoardSlug(value)) {
      throw boardNotFound();
    }
    return value;
  }
}
