// board-server/src/config/environment.spec.ts

/**
 * 환경 변수를 설정으로 바꾸는 함수들(environment.ts)을 검증한다. 서버를 띄우지 않는다.
 */

import {
  DEFAULT_DB_SCHEMA,
  DEFAULT_HOST,
  DEFAULT_JWT_AUDIENCE,
  DEFAULT_JWT_ISSUER,
  DEFAULT_PORT,
  readAuthJwksUrl,
  readDatabaseSettings,
  readDatabaseUrl,
  readDbSchema,
  readEnvironment,
  readHost,
  readJwtAudience,
  readJwtIssuer,
  readPort,
} from './environment.js';

/** 테스트에 쓰는 DB 주소. 실제로 접속하지 않는다 */
const DATABASE_URL = 'postgresql://board:secret-password@127.0.0.1:5432/trpg';
/** 테스트에 쓰는 공개키 주소. 실제로 부르지 않는다 */
const AUTH_JWKS_URL = 'http://127.0.0.1:8000/api/v1/auth/jwks';

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

describe('readDatabaseUrl', () => {
  it.each([undefined, '', '   '])(
    '적지 않으면(%j) 거부한다. 기본값이 없다',
    (value) => {
      expect(() => readDatabaseUrl(value)).toThrow('DATABASE_URL');
    },
  );

  it.each([DATABASE_URL, 'postgres://board:pw@db:5432/trpg'])(
    'PostgreSQL 의 주소(%j)를 그대로 읽는다',
    (value) => {
      expect(readDatabaseUrl(` ${value} `)).toBe(value);
    },
  );

  it.each([
    'mysql://board:pw@127.0.0.1:3306/trpg',
    // 게임 서버(SQLAlchemy)의 주소 모양. 이 서버의 드라이버는 읽지 못한다
    'postgresql+asyncpg://board:pw@127.0.0.1:5432/trpg',
    '127.0.0.1:5432/trpg',
  ])('PostgreSQL 의 주소가 아니면(%j) 거부한다', (value) => {
    expect(() => readDatabaseUrl(value)).toThrow('DATABASE_URL');
  });

  it('거부할 때 받은 값을 예외에 싣지 않는다', () => {
    // 주소에는 비밀번호가 들어 있다. 예외의 글은 화면과 로그에 찍힌다
    expect(() => readDatabaseUrl('mysql://board:secret-password@db')).toThrow(
      expect.not.objectContaining({
        message: expect.stringContaining('secret-password'),
      }),
    );
  });
});

describe('readDbSchema', () => {
  it.each([undefined, '', '  '])('적지 않으면(%j) 개발용 스키마다', (value) => {
    expect(readDbSchema(value)).toBe(DEFAULT_DB_SCHEMA);
  });

  it.each(['board', 'board_test', 'b2'])(
    '스키마 이름(%j)을 읽는다',
    (value) => {
      expect(readDbSchema(` ${value} `)).toBe(value);
    },
  );

  it.each([
    'Board',
    '1board',
    'board-test',
    'board test',
    'board,public',
    // 연결의 설정 글자에 그대로 들어간다. 딴 설정이 끼어들면 안 된다
    'board -c statement_timeout=0',
    'board; DROP SCHEMA board',
    '"board"',
  ])('이름의 모양이 아니면(%j) 거부한다', (value) => {
    expect(() => readDbSchema(value)).toThrow('DB_SCHEMA');
  });
});

describe('readAuthJwksUrl', () => {
  it.each([undefined, '', '   '])('적지 않으면(%j) 예외를 낸다', (value) => {
    expect(() => readAuthJwksUrl(value)).toThrow('AUTH_JWKS_URL');
  });

  it.each([
    'http://127.0.0.1:8000/api/v1/auth/jwks',
    'https://auth.example.com/api/v1/auth/jwks',
    'HTTP://auth:8000/jwks',
  ])('http 나 https 주소(%j)를 받는다', (value) => {
    expect(readAuthJwksUrl(value)).toBe(value);
  });

  it('앞뒤 빈칸 없이 읽는다', () => {
    expect(readAuthJwksUrl(` ${AUTH_JWKS_URL} `)).toBe(AUTH_JWKS_URL);
  });

  it.each([
    '127.0.0.1:8000/api/v1/auth/jwks',
    '/api/v1/auth/jwks',
    'file:///etc/passwd',
    'ftp://auth/jwks',
    'http://',
    'jwks',
  ])('http 나 https 주소가 아니면(%j) 거부한다', (value) => {
    expect(() => readAuthJwksUrl(value)).toThrow('AUTH_JWKS_URL');
  });

  it('거부할 때 받은 값을 예외에 싣지 않는다', () => {
    const value = 'ftp://internal-auth.example.com/jwks';

    expect(() => readAuthJwksUrl(value)).toThrow(
      expect.not.objectContaining({
        message: expect.stringContaining('internal-auth'),
      }),
    );
  });
});

describe('readJwtIssuer', () => {
  it.each([undefined, '', '   '])('적지 않으면(%j) 기본값이다', (value) => {
    expect(readJwtIssuer(value)).toBe(DEFAULT_JWT_ISSUER);
  });

  it('적은 이름을 앞뒤 빈칸 없이 읽는다', () => {
    expect(readJwtIssuer(' other-auth ')).toBe('other-auth');
  });

  it('기본값은 인증 서버의 이름이다', () => {
    expect(DEFAULT_JWT_ISSUER).toBe('ai-trpg-auth');
  });
});

describe('readJwtAudience', () => {
  it.each([undefined, '', '   '])('적지 않으면(%j) 기본값이다', (value) => {
    expect(readJwtAudience(value)).toBe(DEFAULT_JWT_AUDIENCE);
  });

  it('적은 이름을 앞뒤 빈칸 없이 읽는다', () => {
    expect(readJwtAudience(' board-staging ')).toBe('board-staging');
  });

  it('기본값은 게시판 서버의 이름이다', () => {
    expect(DEFAULT_JWT_AUDIENCE).toBe('ai-trpg-board');
  });

  it('여럿을 쉼표로 적으면 거부한다', () => {
    // 인증 서버의 JWT_AUDIENCE(목록)를 그대로 옮겨 적은 실수
    expect(() => readJwtAudience('ai-trpg-auth,ai-trpg-board')).toThrow(
      'JWT_AUDIENCE',
    );
  });
});

describe('readDatabaseSettings', () => {
  it('DB 에 관한 값만 돌려준다', () => {
    const settings = readDatabaseSettings({
      DATABASE_URL,
      DB_SCHEMA: 'board_test',
      PORT: '9000',
    });

    expect(settings).toEqual({ DATABASE_URL, DB_SCHEMA: 'board_test' });
  });

  it('공개키 주소가 없어도 읽는다', () => {
    // 마이그레이션 도구가 쓴다. 인증 서버의 주소 없이도 마이그레이션이 돌아야 한다
    expect(readDatabaseSettings({ DATABASE_URL })).toEqual({
      DATABASE_URL,
      DB_SCHEMA: DEFAULT_DB_SCHEMA,
    });
  });

  it('DB 주소가 없으면 예외를 낸다', () => {
    expect(() => readDatabaseSettings({})).toThrow('DATABASE_URL');
  });
});

describe('readEnvironment', () => {
  it('DB 주소와 공개키 주소만 적어도 나머지는 기본값으로 뜬다', () => {
    expect(readEnvironment({ DATABASE_URL, AUTH_JWKS_URL })).toEqual({
      HOST: DEFAULT_HOST,
      PORT: DEFAULT_PORT,
      DATABASE_URL,
      DB_SCHEMA: DEFAULT_DB_SCHEMA,
      AUTH_JWKS_URL,
      JWT_ISSUER: DEFAULT_JWT_ISSUER,
      JWT_AUDIENCE: DEFAULT_JWT_AUDIENCE,
    });
  });

  it('이 서버가 쓰는 값만 돌려준다', () => {
    const environment = readEnvironment({
      HOST: '0.0.0.0',
      PORT: '9000',
      DATABASE_URL,
      DB_SCHEMA: 'board_test',
      AUTH_JWKS_URL,
      JWT_ISSUER: 'other-auth',
      JWT_AUDIENCE: 'board-staging',
      PATH: '/usr/bin',
    });

    expect(environment).toEqual({
      HOST: '0.0.0.0',
      PORT: 9000,
      DATABASE_URL,
      DB_SCHEMA: 'board_test',
      AUTH_JWKS_URL,
      JWT_ISSUER: 'other-auth',
      JWT_AUDIENCE: 'board-staging',
    });
  });

  it('DB 주소가 없으면 예외를 낸다', () => {
    expect(() => readEnvironment({ AUTH_JWKS_URL })).toThrow('DATABASE_URL');
  });

  it('공개키 주소가 없으면 예외를 낸다', () => {
    expect(() => readEnvironment({ DATABASE_URL })).toThrow('AUTH_JWKS_URL');
  });

  it('틀린 값이 하나라도 있으면 예외를 낸다', () => {
    expect(() =>
      readEnvironment({ DATABASE_URL, AUTH_JWKS_URL, PORT: 'abc' }),
    ).toThrow('PORT');
  });
});
