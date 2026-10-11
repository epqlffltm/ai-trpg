// board-server/src/config/environment.ts

/**
 * 환경 변수를 검사해서 이 서버의 설정으로 바꾼다. Nest 도 .env 도 모르는 순수한 함수들이다.
 *
 * 서버가 뜰 때 한 번 불린다(app.module.ts 의 ConfigModule 이 validate 로 부른다).
 * 마이그레이션 도구는 DB 에 관한 값만 같은 함수로 읽는다(readDatabaseSettings, database/data-source.ts).
 * 서버와 도구가 다른 DB 를 보는 일이 없고, 마이그레이션을 돌리는 데 인증 서버의 주소까지 적지 않아도 된다.
 * 값이 틀리면 예외를 낸다. 서버는 뜨지 않는다. 틀린 설정으로 떠서 요청을 받다가 실패하는 것보다 낫다.
 *
 * 돌려주는 값에는 타입이 붙어 있다. 꺼내 쓰는 쪽은 ConfigService<Environment, true> 로 받는다.
 * 그러면 없는 이름을 꺼내는 것을 컴파일러가 잡고, PORT 가 글자가 아니라 숫자로 나온다.
 */

/** 적지 않았을 때 듣는 주소. 이 컴퓨터 안에서만 닿는다. 컨테이너에서는 0.0.0.0 으로 바꾼다 */
export const DEFAULT_HOST = '127.0.0.1';
/** 적지 않았을 때 듣는 포트. 인증 서버가 8000, 게임 서버가 8001 을 쓴다 */
export const DEFAULT_PORT = 8002;
/** 적지 않았을 때 테이블을 두는 스키마 */
export const DEFAULT_DB_SCHEMA = 'board';
/** 적지 않았을 때 믿는 토큰의 발급자(iss). 인증 서버의 JWT_ISSUER 와 같아야 한다 */
export const DEFAULT_JWT_ISSUER = 'ai-trpg-auth';
/** 적지 않았을 때 이 서버의 이름(aud). 인증 서버의 JWT_AUDIENCE 목록에 이 이름이 있어야 한다 */
export const DEFAULT_JWT_AUDIENCE = 'ai-trpg-board';

/** 포트로 쓸 수 있는 가장 큰 번호 */
const MAX_PORT = 65535;
/** DB 주소가 시작해야 하는 글자들. PostgreSQL 만 쓴다 */
const DATABASE_URL_PREFIXES = ['postgresql://', 'postgres://'];
/**
 * 스키마 이름으로 받는 모양. 영문 소문자로 시작하고 영문 소문자, 숫자, 밑줄만 쓴다.
 * 이 이름은 연결의 설정 글자(search_path)에 그대로 들어간다. 다른 글자를 받으면 그 자리에 딴 설정이 끼어든다.
 */
const SCHEMA_NAME = /^[a-z][a-z0-9_]*$/;
/** 공개키 주소가 쓸 수 있는 방식 */
const JWKS_URL_PROTOCOLS = ['http:', 'https:'];

/** 이 서버의 설정. 이름은 환경 변수의 이름 그대로다. */
export interface Environment {
  HOST: string;
  PORT: number;
  DATABASE_URL: string;
  DB_SCHEMA: string;
  AUTH_JWKS_URL: string;
  JWT_ISSUER: string;
  JWT_AUDIENCE: string;
}

/** DB 에 연결하는 데 필요한 설정. 마이그레이션 도구는 이것만 읽는다. */
export type DatabaseSettings = Pick<Environment, 'DATABASE_URL' | 'DB_SCHEMA'>;

/** 값이 적혀 있는가. 없거나 빈 글자면 적지 않은 것으로 본다. */
function isSet(value: unknown): value is string {
  return typeof value === 'string' && value.trim() !== '';
}

/** 듣는 주소를 읽는다. 적지 않았으면 기본값이다. */
export function readHost(value: unknown): string {
  return isSet(value) ? value.trim() : DEFAULT_HOST;
}

/**
 * 포트를 읽는다. 적지 않았으면 기본값이다.
 *
 * 숫자로만 된 글자여야 하고 1 부터 65535 사이여야 한다. 아니면 예외를 낸다.
 * "80a" 나 "8e3" 같은 글자를 숫자로 너그럽게 읽지 않는다.
 */
export function readPort(value: unknown): number {
  if (!isSet(value)) {
    return DEFAULT_PORT;
  }
  const text = value.trim();
  const port = Number(text);
  if (!/^\d+$/.test(text) || port < 1 || port > MAX_PORT) {
    throw new Error(`PORT 는 1 부터 ${MAX_PORT} 사이의 숫자여야 합니다.`);
  }
  return port;
}

/**
 * DB 접속 주소를 읽는다. 기본값이 없다. 적지 않으면 예외를 낸다.
 *
 * postgresql:// 로 시작해야 한다. 닿는지는 여기서 보지 않는다. 그것은 연결할 때 안다.
 * 예외의 글에 받은 값을 싣지 않는다. 주소에 비밀번호가 들어 있다.
 */
export function readDatabaseUrl(value: unknown): string {
  if (!isSet(value)) {
    throw new Error('DATABASE_URL 을 적어야 합니다.');
  }
  const url = value.trim();
  if (!DATABASE_URL_PREFIXES.some((prefix) => url.startsWith(prefix))) {
    throw new Error('DATABASE_URL 은 postgresql:// 로 시작해야 합니다.');
  }
  return url;
}

/** 테이블을 두는 스키마를 읽는다. 적지 않았으면 기본값이다. 이름의 모양이 틀리면 예외를 낸다. */
export function readDbSchema(value: unknown): string {
  if (!isSet(value)) {
    return DEFAULT_DB_SCHEMA;
  }
  const schema = value.trim();
  if (!SCHEMA_NAME.test(schema)) {
    throw new Error(
      'DB_SCHEMA 는 영문 소문자로 시작하고 영문 소문자, 숫자, 밑줄만 쓸 수 있습니다.',
    );
  }
  return schema;
}

/** 글자가 http 나 https 주소인가. */
function isHttpUrl(text: string): boolean {
  if (!URL.canParse(text)) {
    return false;
  }
  return JWKS_URL_PROTOCOLS.includes(new URL(text).protocol);
}

/**
 * 인증 서버가 공개키를 내주는 주소(JWKS)를 읽는다. 기본값이 없다. 적지 않으면 예외를 낸다.
 *
 * 기본값을 두지 않는 이유: 주소를 잘못 적은 채로 뜨면 토큰을 하나도 검증하지 못하는데,
 * 그 사실을 첫 로그인 요청이 올 때까지 모른다. http:// 나 https:// 주소여야 한다.
 * 닿는지는 여기서 보지 않는다. 인증 서버가 꺼져 있어도 이 서버는 뜬다.
 */
export function readAuthJwksUrl(value: unknown): string {
  if (!isSet(value)) {
    throw new Error('AUTH_JWKS_URL 을 적어야 합니다.');
  }
  const url = value.trim();
  if (!isHttpUrl(url)) {
    throw new Error(
      'AUTH_JWKS_URL 은 http:// 나 https:// 로 시작하는 주소여야 합니다.',
    );
  }
  return url;
}

/** 믿는 토큰의 발급자(iss)를 읽는다. 적지 않았으면 기본값이다. */
export function readJwtIssuer(value: unknown): string {
  return isSet(value) ? value.trim() : DEFAULT_JWT_ISSUER;
}

/**
 * 이 서버의 이름(aud)을 읽는다. 적지 않았으면 기본값이다.
 *
 * 이름은 하나다. 인증 서버는 토큰에 대상의 목록을 싣고, 이 서버는 그 목록에 자기 이름이 있는지만 본다.
 * 쉼표가 든 값은 거부한다. 인증 서버의 JWT_AUDIENCE(목록)를 그대로 옮겨 적은 실수다.
 */
export function readJwtAudience(value: unknown): string {
  if (!isSet(value)) {
    return DEFAULT_JWT_AUDIENCE;
  }
  const audience = value.trim();
  if (audience.includes(',')) {
    throw new Error(
      'JWT_AUDIENCE 에는 이 서버의 이름 하나만 적습니다. 쉼표로 여럿을 적지 않습니다.',
    );
  }
  return audience;
}

/** 환경 변수에서 DB 에 관한 설정만 읽는다. 마이그레이션 도구가 쓴다. 틀린 값이 있으면 예외를 낸다. */
export function readDatabaseSettings(
  variables: Record<string, unknown>,
): DatabaseSettings {
  return {
    DATABASE_URL: readDatabaseUrl(variables.DATABASE_URL),
    DB_SCHEMA: readDbSchema(variables.DB_SCHEMA),
  };
}

/**
 * 환경 변수 전체를 받아 이 서버의 설정을 돌려준다. 틀린 값이 있으면 예외를 낸다.
 *
 * 예외의 글에 값을 싣지 않는다. DB 주소 같은 비밀값이 들어 있다.
 */
export function readEnvironment(
  variables: Record<string, unknown>,
): Environment {
  return {
    HOST: readHost(variables.HOST),
    PORT: readPort(variables.PORT),
    ...readDatabaseSettings(variables),
    AUTH_JWKS_URL: readAuthJwksUrl(variables.AUTH_JWKS_URL),
    JWT_ISSUER: readJwtIssuer(variables.JWT_ISSUER),
    JWT_AUDIENCE: readJwtAudience(variables.JWT_AUDIENCE),
  };
}
