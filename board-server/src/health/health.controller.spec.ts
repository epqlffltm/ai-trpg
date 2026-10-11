// board-server/src/health/health.controller.spec.ts

/**
 * 살아 있는지 확인하는 API 의 답을 검증한다. 서버를 띄우지 않고 메서드를 바로 부른다.
 * 주소와 상태 코드는 test/health.e2e-spec.ts 가 본다.
 */

import { HealthController } from './health.controller.js';

describe('HealthController', () => {
  it('살아 있다고 답한다', () => {
    expect(new HealthController().check()).toEqual({ status: 'ok' });
  });
});
