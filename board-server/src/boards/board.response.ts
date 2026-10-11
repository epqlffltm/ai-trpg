// board-server/src/boards/board.response.ts

/**
 * 게시판을 응답의 모양으로 바꾼다. 순수한 함수다.
 *
 * 칸 이름은 다른 서버들처럼 밑줄로 잇는다(write_policy). 테이블의 번호(id)는 내보내지 않는다.
 * 게시판은 주소의 이름(slug)으로 가리킨다.
 */

import { Board, WritePolicy } from './board.entity.js';

export interface BoardResponse {
  slug: string;
  name: string;
  description: string;
  /** 누가 글을 쓸 수 있는가. member 는 로그인한 누구나, operator 는 운영자만 */
  write_policy: WritePolicy;
}

export function toBoardResponse(board: Board): BoardResponse {
  return {
    slug: board.slug,
    name: board.name,
    description: board.description,
    write_policy: board.writePolicy,
  };
}
