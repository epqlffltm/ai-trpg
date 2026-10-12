// board-server/src/authors/nickname.spec.ts

/**
 * 토큰의 닉네임을 받아들이는 규칙(nickname.ts)을 검증한다.
 */

import { NICKNAME_MAX_LENGTH, readNickname } from './nickname.js';

describe('readNickname', () => {
  it.each(['모험가', 'player_01', 'Kim', '😀'.repeat(NICKNAME_MAX_LENGTH)])(
    '%s 를 받아들인다',
    (nickname) => {
      expect(readNickname(nickname)).toBe(nickname);
    },
  );

  it.each([
    ['글자가 아닌 것', 3],
    ['없는 것', undefined],
    ['null', null],
    ['빈 글자', ''],
    ['빈칸만', '   '],
    ['줄바꿈', '모험\n가'],
    ['NUL', 'a\u0000b'],
    ['방향을 뒤집는 글자', 'abc‮def'],
    ['보이지 않는 글자', 'a​b'],
    ['너무 긴 것', 'a'.repeat(NICKNAME_MAX_LENGTH + 1)],
  ])('%s 은 받지 않는다', (_, value) => {
    expect(readNickname(value)).toBeUndefined();
  });

  it('인증 서버의 길이(20자)보다 넉넉하다', () => {
    expect(NICKNAME_MAX_LENGTH).toBeGreaterThan(20);
  });
});
