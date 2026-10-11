// board-server/src/database/data-source.ts

/**
 * 마이그레이션 도구(TypeORM CLI)가 읽는 연결. 서버는 이 파일을 쓰지 않는다.
 *
 * 도구는 Nest 밖에서 돈다. 그래서 설정을 여기서 직접 읽는다. 읽는 함수와 옵션을 만드는 함수는 서버와 같은 것이다.
 *   - DB 에 관한 값만 읽는다(readDatabaseSettings). 인증 서버의 주소 같은 값은 없어도 마이그레이션이 돈다.
 *   - .env 가 있으면 읽는다. 이미 정해진 환경 변수는 덮어쓰지 않는다.
 *     그래서 DB_SCHEMA=board_test 를 앞에 붙여 부르면 테스트용 스키마에 적용된다.
 *   - 도구는 빌드된 파일(dist/)을 읽는다. 엔티티와 마이그레이션도 빌드된 것을 이 파일의 위치에서 찾는다.
 *     타입스크립트 파일을 바로 읽게 하려면 도구가 하나 더 필요하고, 데코레이터와 ESM 을 함께 다루는 설정이 까다롭다.
 *
 * 쓰는 법은 package.json 의 migration:* 명령과 README 의 "DB와 마이그레이션"에 있다.
 */

import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { DataSource } from 'typeorm';
import { readDatabaseSettings } from '../config/environment.js';
import { databaseOptions } from './database.options.js';

/** 개발자의 설정 파일. 이 명령을 부르는 폴더(board-server)에서 찾는다 */
const ENV_FILE = '.env';

if (existsSync(ENV_FILE)) {
  process.loadEnvFile(ENV_FILE);
}

/** 빌드된 파일들이 놓인 폴더(dist). 이 파일은 dist/database 에 있다 */
const BUILD_ROOT = join(import.meta.dirname, '..');

export default new DataSource({
  ...databaseOptions(readDatabaseSettings(process.env)),
  entities: [join(BUILD_ROOT, '**', '*.entity.js')],
  migrations: [join(BUILD_ROOT, 'migrations', '*.js')],
});
