// board-server/test/setup.ts

/**
 * 앱을 통째로 만드는 테스트(*.e2e-spec.ts)가 돌기 전에 환경 변수를 맞춘다. 테스트 파일마다 먼저 돈다.
 *
 * 테스트는 실제 PostgreSQL 에서 돈다. 개발용과 같은 DB 를 쓰되 스키마를 나눈다.
 * 개발용 데이터는 board 스키마에, 테스트는 board_test 스키마에 있다.
 *
 *   - DB 주소는 개발 환경의 것(환경 변수, 없으면 .env)을 그대로 읽는다. 비밀번호를 테스트 코드에 적지 않는다.
 *   - 동작을 바꾸는 값은 여기서 고정한다. 개발자의 .env 에 무엇이 적혀 있든 테스트 결과가 같아야 한다.
 *     그래서 .env 를 통째로 읽지 않고 DB 주소만 골라 읽는다.
 *   - 인증 서버는 띄우지 않는다. 공개키 주소는 닿지 않는 주소로 고정하고, 토큰은 테스트가 만든 키로 서명한다.
 */

import { existsSync, readFileSync } from 'node:fs';
import { parseEnv } from 'node:util';

/** 테스트가 쓰는 스키마. 개발용 데이터(board 스키마)를 건드리지 않는다 */
export const TEST_SCHEMA = 'board_test';

/**
 * 테스트가 쓰는 공개키 주소. 실제로 부르지 않는다. 키를 가져오는 함수는 테스트가 가짜로 바꿔 꽂는다(test/app.ts).
 * .invalid 는 어디에도 닿지 않게 되어 있는 이름이다(RFC 2606). 바꿔 꽂기를 빠뜨려도 실제 인증 서버를 부르지 않는다
 */
export const TEST_JWKS_URL = 'http://auth.invalid/api/v1/auth/jwks';

/** 개발자의 설정 파일. 테스트를 돌리는 폴더(board-server)에서 찾는다 */
const ENV_FILE = '.env';

/** .env 에 적힌 DB 주소. 파일이 없거나 적혀 있지 않으면 undefined 다. */
function databaseUrlFromEnvFile(): string | undefined {
  if (!existsSync(ENV_FILE)) {
    return undefined;
  }
  return parseEnv(readFileSync(ENV_FILE, 'utf8')).DATABASE_URL;
}

const databaseUrl = process.env.DATABASE_URL ?? databaseUrlFromEnvFile();
if (databaseUrl !== undefined) {
  process.env.DATABASE_URL = databaseUrl;
}
process.env.DB_SCHEMA = TEST_SCHEMA;
process.env.AUTH_JWKS_URL = TEST_JWKS_URL;
// 개발자의 환경에 남아 있을 수 있는 값을 지운다. 테스트는 기본값으로 돈다
delete process.env.HOST;
delete process.env.PORT;
delete process.env.JWT_ISSUER;
delete process.env.JWT_AUDIENCE;
delete process.env.APP_ENVIRONMENT;
delete process.env.APP_VERSION;
delete process.env.LOG_LEVEL;
// 알림 서버는 부르지 않는다. 알림은 발송함에 적히기만 한다. 보내는 것을 보는 테스트는 가짜를 꽂는다
delete process.env.NOTIFICATION_URL;
delete process.env.NOTIFICATION_SECRET;
