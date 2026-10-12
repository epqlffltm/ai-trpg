// board-server/test/app.ts

/**
 * 테스트가 앱을 만들 때 함께 쓰는 도구.
 *
 * 서버를 띄울 때와 같은 규칙을 건다(setupApp). 네트워크의 포트는 열지 않는다.
 * 요청은 supertest 가 앱에 바로 넘긴다.
 */

import { Type } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { NestExpressApplication } from '@nestjs/platform-express';
import { Test, TestingModuleBuilder } from '@nestjs/testing';
import { AppModule } from '../src/app.module.js';
import { setupApp } from '../src/app.setup.js';
import { JWKS_LOADER } from '../src/auth/auth.module.js';
import { JwksFetchError, LoadKeys } from '../src/auth/jwks.js';
import { Environment } from '../src/config/environment.js';
import {
  WRITE_LIMITS,
  WriteLimits,
} from '../src/write-limits/write-limits.policy.js';
import { WRITE_LIMITS_TOKEN } from '../src/write-limits/write-limits.service.js';
import { TEST_SCHEMA } from './setup.js';

/** 앱을 만들기 전에 부품을 바꿔 꽂는 함수. 가짜 DB 확인기 같은 것을 꽂는다 */
export type Customize = (builder: TestingModuleBuilder) => TestingModuleBuilder;

/**
 * 테스트용 앱이 기본으로 쓰는, 키를 가져오는 함수. 늘 받지 못한다. 테스트는 인증 서버를 부르지 않는다.
 * 토큰을 쓰는 테스트는 자기가 만든 키를 내주는 함수로 바꿔 꽂는다(useKeys).
 */
const noAuthServer: LoadKeys = () =>
  Promise.reject(new JwksFetchError('테스트는 인증 서버를 부르지 않는다'));

/** 키를 가져오는 함수를 바꿔 꽂는다. createTestApp 에 넘긴다. */
export function useKeys(load: LoadKeys): Customize {
  return (builder) => builder.overrideProvider(JWKS_LOADER).useValue(load);
}

/**
 * 테스트용 앱이 기본으로 쓰는 쓰기 한도. 걸리지 않을 만큼 크다.
 * 글과 댓글을 수십 개 써 보거나 신고를 여러 번 해 보는 테스트가 도배를 막는 한도에 걸리면 안 된다.
 */
const NO_WRITE_LIMITS: WriteLimits = {
  post: { windowSeconds: 1, max: 1_000_000 },
  comment: { windowSeconds: 1, max: 1_000_000 },
  report: { windowSeconds: 1, max: 1_000_000 },
};

/** 쓰기 한도를 바꿔 꽂는다. createTestApp 에 넘긴다. */
export function useWriteLimits(limits: WriteLimits): Customize {
  return (builder) =>
    builder.overrideProvider(WRITE_LIMITS_TOKEN).useValue(limits);
}

/** 서버가 쓰는 쓰기 한도를 그대로 쓴다. 한도를 보는 테스트가 createTestApp 에 넘긴다. */
export const useRealWriteLimits: Customize = useWriteLimits(WRITE_LIMITS);

/** 여러 가지를 차례로 바꿔 꽂는다. */
export function both(...customizations: Customize[]): Customize {
  return (builder) =>
    customizations.reduce((built, customize) => customize(built), builder);
}

/**
 * 테스트용 앱을 만든다. 다 쓴 뒤에 app.close() 로 닫는다. 닫지 않으면 DB 연결이 남는다.
 *
 * 설정을 잘못 건드려 개발용 스키마에서 테스트가 도는 일을 막는다. 테스트용 스키마가 아니면 만들지 않는다.
 * probes 는 앱 모듈 옆에 더할 시험용 모듈이다. 앱 전체에 건 규칙이 새 컨트롤러에도 걸리는지 볼 때 쓴다.
 */
export async function createTestApp(
  customize: Customize = (builder) => builder,
  probes: Type[] = [],
): Promise<NestExpressApplication> {
  const builder = both(
    useKeys(noAuthServer),
    useWriteLimits(NO_WRITE_LIMITS),
  )(Test.createTestingModule({ imports: [AppModule, ...probes] }));
  const module = await customize(builder).compile();
  const app = module.createNestApplication<NestExpressApplication>();
  // 테스트가 도는 동안에는 경고와 오류만 화면에 찍는다. 요청마다 한 줄씩 남는 로그가 테스트의 결과를 가린다.
  // 로그를 보는 테스트는 줄을 모으는 로거를 따로 꽂는다(app.useLogger)
  app.useLogger(['warn', 'error', 'fatal']);
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
