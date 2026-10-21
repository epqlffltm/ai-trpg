// board-server/src/authors/nicknames.spec.ts

/**
 * 사용자 번호로 닉네임을 찾는 표(nicknames.ts)를 검증한다.
 */

import {
  knownAuthors,
  nicknameOf,
  nicknamesFrom,
  NO_NICKNAMES,
} from './nicknames.js';

const USER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const STRANGER = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';

describe('nicknameOf', () => {
  it('표에 있는 사람의 이름을 찾는다', () => {
    const nicknames = nicknamesFrom([{ userId: USER, nickname: '모험가' }]);

    expect(nicknameOf(nicknames, USER)).toBe('모험가');
  });

  it('모르는 사람은 null 이다', () => {
    expect(nicknameOf(NO_NICKNAMES, STRANGER)).toBeNull();
  });

  it('탈퇴한 사람(번호가 비었다)은 null 이다', () => {
    const nicknames = nicknamesFrom([{ userId: USER, nickname: '모험가' }]);

    expect(nicknameOf(nicknames, null)).toBeNull();
  });
});

describe('knownAuthors', () => {
  it('탈퇴해 빈 자리와 겹친 번호를 뺀다', () => {
    expect(knownAuthors([USER, null, STRANGER, USER, null])).toEqual([
      USER,
      STRANGER,
    ]);
  });
});
