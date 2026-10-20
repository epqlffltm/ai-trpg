// board-server/src/database/database.module.ts

/**
 * DB 연결을 맡는 모듈. TypeORM 의 연결(DataSource)을 앱에 하나 만들어 둔다.
 *
 * 연결 옵션은 설정에서 만든다(database.options.ts). 설정이 준비된 뒤에 만들어야 해서 forRootAsync 를 쓴다.
 *   - autoLoadEntities: 기능 모듈이 TypeOrmModule.forFeature 로 등록한 엔티티를 알아서 모은다.
 *     엔티티의 목록을 한곳에 손으로 적지 않는다.
 *   - 서버가 뜰 때 DB 에 연결해 본다. 닿지 않으면 몇 번 다시 해 보고(RETRY_ATTEMPTS) 그래도 안 되면 뜨지 않는다.
 *     Nest 의 기본은 3초 간격으로 10번(30초)이다. 개발할 때 DB 를 안 켰다는 것을 빨리 알도록 줄였다.
 *
 * 떠 있는 동안 DB 가 끊기면 서버는 죽지 않는다. 쿼리가 실패하고, 준비됐는지 묻는 API 가 503 을 돌려준다.
 * DB 가 돌아오면 다음 쿼리부터 다시 된다. 연결의 묶음(풀)이 새 연결을 맺는다.
 */

import { Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { TypeOrmModule, TypeOrmModuleOptions } from '@nestjs/typeorm';
import { Environment } from '../config/environment.js';
import { DatabaseHealth } from './database.health.js';
import { databaseOptions } from './database.options.js';
import { PoolWatch } from './pool-watch.js';

/** 뜰 때 DB 에 연결을 몇 번까지 다시 해 보나 */
const RETRY_ATTEMPTS = 3;
/** 다시 해 보기 전에 쉬는 시간(밀리초) */
const RETRY_DELAY_MS = 1000;

/** 설정에서 Nest 용 연결 옵션을 만든다. */
export function typeOrmOptions(
  config: ConfigService<Environment, true>,
): TypeOrmModuleOptions {
  return {
    ...databaseOptions({
      DATABASE_URL: config.get('DATABASE_URL', { infer: true }),
      DB_SCHEMA: config.get('DB_SCHEMA', { infer: true }),
    }),
    autoLoadEntities: true,
    retryAttempts: RETRY_ATTEMPTS,
    retryDelay: RETRY_DELAY_MS,
  };
}

@Module({
  imports: [
    TypeOrmModule.forRootAsync({
      inject: [ConfigService],
      useFactory: typeOrmOptions,
    }),
  ],
  providers: [DatabaseHealth, PoolWatch],
  exports: [DatabaseHealth],
})
export class DatabaseModule {}
