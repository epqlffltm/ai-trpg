// board-server/src/boards/board.response.spec.ts

/**
 * 게시판을 응답의 모양으로 바꾸는 함수(board.response.ts)를 검증한다.
 */

import { Board } from './board.entity.js';
import { toBoardResponse } from './board.response.js';

describe('toBoardResponse', () => {
  it('주소의 이름과 보여 줄 값만 내보낸다', () => {
    const board: Board = {
      id: 7,
      slug: 'notice',
      name: '공지사항',
      description: '운영자가 알리는 소식입니다.',
      writePolicy: 'operator',
      position: 1,
      createdAt: new Date('2026-10-11T00:00:00.000Z'),
    };

    // 테이블의 번호(id)와 차례(position)는 내보내지 않는다
    expect(toBoardResponse(board)).toEqual({
      slug: 'notice',
      name: '공지사항',
      description: '운영자가 알리는 소식입니다.',
      write_policy: 'operator',
    });
  });
});
