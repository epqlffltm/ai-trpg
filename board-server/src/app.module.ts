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
 *
 * 로그인은 기본으로 필요하다. AuthModule 이 문지기를 앱 전체에 건다. 열어 둘 API 에만 @Public() 을 붙인다.
 *
 * 앱 전체에 거는 규칙이 둘 더 있다. 테스트가 만드는 앱에도 똑같이 걸리도록 여기에 적는다.
 *   - APP_PIPE: 요청의 입력을 DTO 의 규칙대로 검사한다(errors/validation.ts).
 *   - APP_FILTER: 예외를 { detail } 모양의 응답으로 바꾼다(errors/all-exceptions.filter.ts).
 */

import { Module } from '@nestjs/common';
import { APP_FILTER, APP_PIPE } from '@nestjs/core';
import { ConfigModule } from '@nestjs/config';
import { AuthModule } from './auth/auth.module.js';
import { BoardsModule } from './boards/boards.module.js';
import { readEnvironment } from './config/environment.js';
import { DatabaseModule } from './database/database.module.js';
import { AllExceptionsFilter } from './errors/all-exceptions.filter.js';
import { validationPipe } from './errors/validation.js';
import { HealthModule } from './health/health.module.js';
import { MeModule } from './me/me.module.js';
import { PostsModule } from './posts/posts.module.js';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      validate: readEnvironment,
      ignoreEnvFile: process.env.NODE_ENV === 'test',
    }),
    DatabaseModule,
    AuthModule,
    HealthModule,
    MeModule,
    BoardsModule,
    PostsModule,
  ],
  providers: [
    { provide: APP_PIPE, useFactory: validationPipe },
    { provide: APP_FILTER, useClass: AllExceptionsFilter },
  ],
})
export class AppModule {}
