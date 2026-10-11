// board-server/test/app.ts

/**
 * 테스트가 앱을 만들 때 함께 쓰는 도구.
 *
 * 서버를 띄울 때와 같은 규칙을 건다(setupApp). 네트워크의 포트는 열지 않는다.
 * 요청은 supertest 가 앱에 바로 넘긴다.
 */

import { ConfigService } from '@nestjs/config';
import { NestExpressApplication } from '@nestjs/platform-express';
import { Test, TestingModuleBuilder } from '@nestjs/testing';
import { AppModule } from '../src/app.module.js';
import { setupApp } from '../src/app.setup.js';
import { Environment } from '../src/config/environment.js';
import { TEST_SCHEMA } from './setup.js';

/** 앱을 만들기 전에 부품을 바꿔 꽂는 함수. 가짜 DB 확인기 같은 것을 꽂는다 */
export type Customize = (builder: TestingModuleBuilder) => TestingModuleBuilder;

/**
 * 테스트용 앱을 만든다. 다 쓴 뒤에 app.close() 로 닫는다. 닫지 않으면 DB 연결이 남는다.
 *
 * 설정을 잘못 건드려 개발용 스키마에서 테스트가 도는 일을 막는다. 테스트용 스키마가 아니면 만들지 않는다.
 */
export async function createTestApp(
  customize: Customize = (builder) => builder,
): Promise<NestExpressApplication> {
  const builder = Test.createTestingModule({ imports: [AppModule] });
  const module = await customize(builder).compile();
  const app = module.createNestApplication<NestExpressApplication>();
  setupApp(app);
  await app.init();

  const config = app.get<ConfigService<Environment, true>>(ConfigService);
  const schema = config.get('DB_SCHEMA', { infer: true });
  if (schema !== TEST_SCHEMA) {
    await app.close();
    throw new Error('테스트는 테스트용 스키마에서만 돈다');
  }
  return app;
}
