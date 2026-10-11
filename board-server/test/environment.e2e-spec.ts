// board-server/test/environment.e2e-spec.ts

/**
 * 설정이 틀리면 앱이 만들어지지 않는지 본다. 검사하는 함수가 앱에 실제로 물려 있는지 확인한다.
 * 함수 자체의 규칙은 src/config/environment.spec.ts 가 본다.
 *
 * 설정은 app.module.ts 를 불러올 때 읽는다. 그래서 환경 변수를 바꾼 뒤에 모듈을 새로 불러온다.
 * 틀린 값의 예외는 불러올 때가 아니라 Nest 가 그 모듈로 앱을 만들 때 올라온다.
 */

import { Test } from '@nestjs/testing';

/** 지금의 환경 변수로 앱 모듈을 새로 불러와 앱을 만들어 본다. */
async function compileApp(): Promise<void> {
  vi.resetModules();
  const { AppModule } = await import('../src/app.module.js');
  const module = await Test.createTestingModule({
    imports: [AppModule],
  }).compile();
  await module.close();
}

describe('설정이 틀린 서버', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('포트가 숫자가 아니면 앱이 만들어지지 않는다', async () => {
    vi.stubEnv('PORT', 'abc');

    await expect(compileApp()).rejects.toThrow('PORT');
  });

  it('포트를 적지 않으면 기본값으로 만들어진다', async () => {
    vi.stubEnv('PORT', '');

    await expect(compileApp()).resolves.toBeUndefined();
  });
});
