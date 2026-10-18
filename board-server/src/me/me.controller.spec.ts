// board-server/src/me/me.controller.spec.ts

/**
 * 토큰의 주인을 돌려주는 API 를 검증한다. 서버를 띄우지 않는다.
 * 토큰을 검증하는 일과 상태 코드는 test/auth.e2e-spec.ts 가 본다.
 */

import { MeController } from './me.controller.js';

/** 토큰에서 꺼낸 값. 운영자인지만 바꿔 본다. */
function claims(isOperator: boolean) {
  return {
    userId: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
    expiresAt: new Date('2027-01-15T08:00:00.000Z'),
    version: 1,
    isOperator,
  };
}

describe('MeController', () => {
  it('토큰의 주인의 ID 와 운영자가 아님을 돌려준다', () => {
    expect(new MeController().readMe(claims(false))).toEqual({
      user_id: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
      is_operator: false,
    });
  });

  it('운영자면 is_operator 가 참이다', () => {
    expect(new MeController().readMe(claims(true)).is_operator).toBe(true);
  });
});
