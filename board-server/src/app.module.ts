// board-server/src/app.module.ts

/**
 * 앱 모듈. 이 서버를 이루는 모듈들을 모은다. 기능을 더할 때마다 여기에 그 모듈을 적는다.
 *
 * 설정은 @nestjs/config 의 ConfigModule 이 읽는다.
 *   - .env 파일과 환경 변수를 읽어 readEnvironment(config/environment.ts)에 넘긴다. 값이 틀리면 예외가 나고
 *     서버는 뜨지 않는다. 예외는 Nest 가 이 모듈로 앱을 만들 때(NestFactory.create) 올라온다.
 *   - isGlobal: 설정을 쓰는 모듈마다 ConfigModule 을 다시 적지 않아도 된다.
 *   - 테스트는 .env 를 통째로 읽지 않는다(ignoreEnvFile). 개발자의 .env 에 무엇이 적혀 있든 결과가 같아야 한다.
 *     테스트를 돌리는 도구(vitest)가 NODE_ENV 를 test 로 둔다. DB 주소만은 test/setup.ts 가 골라 읽는다.
 */

import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { readEnvironment } from './config/environment.js';
import { DatabaseModule } from './database/database.module.js';
import { HealthModule } from './health/health.module.js';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      validate: readEnvironment,
      ignoreEnvFile: process.env.NODE_ENV === 'test',
    }),
    DatabaseModule,
    HealthModule,
  ],
})
export class AppModule {}
