// board-server/src/config/environment.spec.ts

/**
 * 환경 변수를 설정으로 바꾸는 함수들(environment.ts)을 검증한다. 서버를 띄우지 않는다.
 */

import {
  DEFAULT_APP_ENVIRONMENT,
  DEFAULT_APP_VERSION,
  DEFAULT_DB_SCHEMA,
  DEFAULT_HOST,
  DEFAULT_JWT_AUDIENCE,
  DEFAULT_JWT_ISSUER,
  DEFAULT_LOG_LEVEL,
  DEFAULT_METRIC_EXPORT_INTERVAL,
  DEFAULT_PORT,
  readAppEnvironment,
  readAppVersion,
  readAuthJwksUrl,
  readDatabaseSettings,
  readDatabaseUrl,
  readDbSchema,
  readEnvironment,
  readHost,
  readJwtAudience,
  readJwtIssuer,
  readLogLevel,
  readMetricExportInterval,
  readNotificationSettings,
  readOtlpEndpoint,
  readPort,
  readSessionRevocationsUrl,
} from './environment.js';

/** 테스트에 쓰는 DB 주소. 실제로 접속하지 않는다 */
const DATABASE_URL = 'postgresql://board:secret-password@127.0.0.1:5432/trpg';
/** 테스트에 쓰는 공개키 주소. 실제로 부르지 않는다 */
const AUTH_JWKS_URL = 'http://127.0.0.1:8000/api/v1/auth/jwks';
/** 공개키 주소의 옆. 끊긴 세션의 목록을 내주는 주소다 */
const AUTH_SESSION_REVOCATIONS_URL =
  'http://127.0.0.1:8000/api/v1/auth/session-revocations';

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

describe('readSessionRevocationsUrl', () => {
  it('적지 않으면 공개키 주소의 옆이다', () => {
    expect(readSessionRevocationsUrl(undefined, AUTH_JWKS_URL)).toBe(
      AUTH_SESSION_REVOCATIONS_URL,
    );
    expect(readSessionRevocationsUrl('  ', AUTH_JWKS_URL)).toBe(
      AUTH_SESSION_REVOCATIONS_URL,
    );
  });

  it('적으면 그 주소다', () => {
    const url = 'https://auth.example.com/revoked';

    expect(readSessionRevocationsUrl(` ${url} `, AUTH_JWKS_URL)).toBe(url);
  });

  it('http 나 https 주소가 아니면 뜨지 않는다', () => {
    expect(() =>
      readSessionRevocationsUrl('ftp://auth/revoked', AUTH_JWKS_URL),
    ).toThrow('AUTH_SESSION_REVOCATIONS_URL');
  });

  it.each([
    'http://127.0.0.1:8000/keys.json',
    'http://127.0.0.1:8000/api/v1/auth/jwks?v=2',
  ])('공개키 주소가 /jwks 로 끝나지 않으면 적어야 한다: %s', (jwksUrl) => {
    expect(() => readSessionRevocationsUrl(undefined, jwksUrl)).toThrow(
      'AUTH_SESSION_REVOCATIONS_URL 을 적어야 합니다',
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

describe('readAppEnvironment', () => {
  it.each([undefined, '', '   '])('적지 않으면(%j) development 다', (value) => {
    expect(readAppEnvironment(value)).toBe(DEFAULT_APP_ENVIRONMENT);
    expect(DEFAULT_APP_ENVIRONMENT).toBe('development');
  });

  it.each(['production', 'staging', 'test', 'dev-2', 'qa_1'])(
    '환경의 이름(%j)을 읽는다',
    (value) => {
      expect(readAppEnvironment(` ${value} `)).toBe(value);
    },
  );

  it.each([
    'Production',
    '1st',
    'prod uction',
    'prod\n{"level":"error"}',
    'a'.repeat(33),
  ])('이름의 모양이 아니면(%j) 거부한다', (value) => {
    // 이 값은 로그의 모든 줄에 실린다. 줄바꿈이 든 값을 받지 않는다
    expect(() => readAppEnvironment(value)).toThrow('APP_ENVIRONMENT');
  });
});

describe('readAppVersion', () => {
  it.each([undefined, '', '   '])('적지 않으면(%j) dev 다', (value) => {
    expect(readAppVersion(value)).toBe(DEFAULT_APP_VERSION);
    expect(DEFAULT_APP_VERSION).toBe('dev');
  });

  it.each(['3f2a1b9', 'v1.2.3', '1.0.0+build.5', '2026-10-11_1'])(
    '버전(%j)을 읽는다',
    (value) => {
      expect(readAppVersion(value)).toBe(value);
    },
  );

  it.each(['v1 beta', 'v1\nforged', 'a'.repeat(65), 'v1/2', '"quoted"'])(
    '버전의 모양이 아니면(%j) 거부한다',
    (value) => {
      expect(() => readAppVersion(value)).toThrow('APP_VERSION');
    },
  );
});

describe('readLogLevel', () => {
  it.each([undefined, '', '   '])('적지 않으면(%j) info 다', (value) => {
    expect(readLogLevel(value)).toBe(DEFAULT_LOG_LEVEL);
    expect(DEFAULT_LOG_LEVEL).toBe('info');
  });

  it.each([
    ['debug', 'debug'],
    ['info', 'info'],
    ['warning', 'warning'],
    ['error', 'error'],
    [' WARNING ', 'warning'],
  ])('수준(%j)을 읽는다', (value, level) => {
    expect(readLogLevel(value)).toBe(level);
  });

  it.each(['warn', 'verbose', 'trace', '3', 'critical'])(
    '정해 둔 수준이 아니면(%j) 거부한다',
    (value) => {
      expect(() => readLogLevel(value)).toThrow('LOG_LEVEL');
    },
  );
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
      AUTH_SESSION_REVOCATIONS_URL,
      JWT_ISSUER: DEFAULT_JWT_ISSUER,
      JWT_AUDIENCE: DEFAULT_JWT_AUDIENCE,
      APP_ENVIRONMENT: DEFAULT_APP_ENVIRONMENT,
      APP_VERSION: DEFAULT_APP_VERSION,
      LOG_LEVEL: DEFAULT_LOG_LEVEL,
      NOTIFICATION_URL: '',
      NOTIFICATION_SECRET: '',
      OTEL_EXPORTER_OTLP_ENDPOINT: '',
      OTEL_METRIC_EXPORT_INTERVAL: DEFAULT_METRIC_EXPORT_INTERVAL,
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
      APP_ENVIRONMENT: 'production',
      APP_VERSION: '3f2a1b9',
      LOG_LEVEL: 'warning',
      NOTIFICATION_URL: 'http://notification:8004',
      NOTIFICATION_SECRET: SECRET,
      OTEL_EXPORTER_OTLP_ENDPOINT: 'http://alloy:4318/',
      OTEL_METRIC_EXPORT_INTERVAL: '5000',
      PATH: '/usr/bin',
    });

    expect(environment).toEqual({
      HOST: '0.0.0.0',
      PORT: 9000,
      DATABASE_URL,
      DB_SCHEMA: 'board_test',
      AUTH_JWKS_URL,
      AUTH_SESSION_REVOCATIONS_URL,
      JWT_ISSUER: 'other-auth',
      JWT_AUDIENCE: 'board-staging',
      APP_ENVIRONMENT: 'production',
      APP_VERSION: '3f2a1b9',
      LOG_LEVEL: 'warning',
      NOTIFICATION_URL: 'http://notification:8004',
      NOTIFICATION_SECRET: SECRET,
      OTEL_EXPORTER_OTLP_ENDPOINT: 'http://alloy:4318',
      OTEL_METRIC_EXPORT_INTERVAL: 5000,
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

/** 알림 서버의 비밀로 쓰는 32자 넘는 글자. 테스트에서만 쓴다 */
const SECRET = 'board-notification-test-secret-of-32';

describe('readNotificationSettings', () => {
  it('주소를 적지 않으면 둘 다 빈 글자다. 알림을 적기만 한다', () => {
    expect(readNotificationSettings(undefined, SECRET)).toEqual({
      NOTIFICATION_URL: '',
      NOTIFICATION_SECRET: '',
    });
    expect(readNotificationSettings('  ', undefined)).toEqual({
      NOTIFICATION_URL: '',
      NOTIFICATION_SECRET: '',
    });
  });

  it('주소와 비밀을 앞뒤 빈칸 없이 읽는다', () => {
    expect(
      readNotificationSettings(' http://notification:8004 ', ` ${SECRET} `),
    ).toEqual({
      NOTIFICATION_URL: 'http://notification:8004',
      NOTIFICATION_SECRET: SECRET,
    });
  });

  it('http 가 아닌 주소는 받지 않는다', () => {
    expect(() =>
      readNotificationSettings('file:///etc/passwd', SECRET),
    ).toThrow('NOTIFICATION_URL');
  });

  it('주소를 적었는데 비밀이 없거나 짧으면 뜨지 않는다. 비밀은 예외에 싣지 않는다', () => {
    expect(() =>
      readNotificationSettings('http://notification:8004', undefined),
    ).toThrow('NOTIFICATION_SECRET');
    expect(() =>
      readNotificationSettings('http://notification:8004', 'short-secret'),
    ).toThrow(/^(?!.*short-secret)/);
  });
});

describe('readMetricExportInterval', () => {
  it('적지 않으면 15초다', () => {
    expect(readMetricExportInterval(undefined)).toBe(15000);
    expect(readMetricExportInterval(' ')).toBe(15000);
  });

  it('1000 이상의 숫자를 받는다', () => {
    expect(readMetricExportInterval('1000')).toBe(1000);
    expect(readMetricExportInterval(' 60000 ')).toBe(60000);
  });

  it.each(['999', '0', '-1000', '15s', '1e4', '1500.5'])(
    '%s 는 받지 않는다',
    (value) => {
      expect(() => readMetricExportInterval(value)).toThrow('1000(밀리초)');
    },
  );
});

describe('readOtlpEndpoint', () => {
  it('적지 않으면 빈 글자다. span 을 내보내지 않는다', () => {
    expect(readOtlpEndpoint(undefined)).toBe('');
    expect(readOtlpEndpoint('  ')).toBe('');
  });

  it.each([
    ['http://alloy:4318', 'http://alloy:4318'],
    ['https://otlp.example.com/', 'https://otlp.example.com'],
    [' http://127.0.0.1:4318 ', 'http://127.0.0.1:4318'],
  ])('%j 를 %j 로 읽는다. 끝의 / 는 뗀다', (value, expected) => {
    expect(readOtlpEndpoint(value)).toBe(expected);
  });

  it.each(['alloy:4318', 'ftp://alloy:4318', 'not a url'])(
    'http 나 https 주소가 아닌 %j 는 받지 않는다',
    (value) => {
      expect(() => readOtlpEndpoint(value)).toThrow('http://');
    },
  );

  it.each([
    'http://alloy:4318/v1/traces',
    'http://alloy:4318/?a=b',
    'http://alloy:4318/#x',
  ])(
    '경로가 있는 %j 는 받지 않는다. /v1/traces 는 보내는 쪽이 붙인다',
    (value) => {
      expect(() => readOtlpEndpoint(value)).toThrow('경로 없이');
    },
  );
});
