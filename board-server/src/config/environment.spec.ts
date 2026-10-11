// board-server/src/config/environment.spec.ts

/**
 * 환경 변수를 설정으로 바꾸는 함수들(environment.ts)을 검증한다. 서버를 띄우지 않는다.
 */

import {
  DEFAULT_HOST,
  DEFAULT_PORT,
  readEnvironment,
  readHost,
  readPort,
} from './environment.js';

describe('readPort', () => {
  it.each([undefined, '', '   '])('적지 않으면(%j) 기본 포트다', (value) => {
    expect(readPort(value)).toBe(DEFAULT_PORT);
  });

  it.each([
    ['8002', 8002],
    [' 3000 ', 3000],
    ['1', 1],
    ['65535', 65535],
  ])('숫자로 된 글자(%j)를 숫자로 읽는다', (value, port) => {
    expect(readPort(value)).toBe(port);
  });

  it.each(['abc', '80a', '8e3', '-1', '0', '65536', '80.5', '0x50'])(
    '포트가 될 수 없는 값(%j)은 거부한다',
    (value) => {
      expect(() => readPort(value)).toThrow('PORT');
    },
  );

  it('거부할 때 받은 값을 예외에 싣지 않는다', () => {
    expect(() => readPort('secret-value')).toThrow(
      expect.not.objectContaining({
        message: expect.stringContaining('secret-value'),
      }),
    );
  });
});

describe('readHost', () => {
  it.each([undefined, '', '  '])(
    '적지 않으면(%j) 이 컴퓨터 안에서만 닿는 주소다',
    (value) => {
      expect(readHost(value)).toBe(DEFAULT_HOST);
    },
  );

  it('적은 주소를 앞뒤 빈칸 없이 읽는다', () => {
    expect(readHost(' 0.0.0.0 ')).toBe('0.0.0.0');
  });
});

describe('readEnvironment', () => {
  it('아무것도 적지 않아도 기본값으로 뜬다', () => {
    expect(readEnvironment({})).toEqual({
      HOST: DEFAULT_HOST,
      PORT: DEFAULT_PORT,
    });
  });

  it('이 서버가 쓰는 값만 돌려준다', () => {
    const environment = readEnvironment({
      HOST: '0.0.0.0',
      PORT: '9000',
      PATH: '/usr/bin',
    });

    expect(environment).toEqual({ HOST: '0.0.0.0', PORT: 9000 });
  });

  it('틀린 값이 하나라도 있으면 예외를 낸다', () => {
    expect(() => readEnvironment({ PORT: 'abc' })).toThrow('PORT');
  });
});
