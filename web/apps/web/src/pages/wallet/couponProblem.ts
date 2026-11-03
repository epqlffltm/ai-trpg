// web/apps/web/src/pages/wallet/couponProblem.ts
// 쿠폰을 받지 못한 까닭을 화면의 한 줄로(#979). 순수한 함수다. 까닭은 결제 서버의 code 다(api/coupons.ts).
// 본인인증 전이면 화면이 본인인증으로 가는 길을 붙인다(verify).

import { ApiError, NetworkError } from '../../api/errors';

export type CouponProblem = { message: string; verify: boolean };

const BY_CODE: Record<string, string> = {
  'coupon.not_found': '그런 쿠폰이 없습니다. 코드를 다시 확인해 주세요.',
  'coupon.already_redeemed': '이미 받은 쿠폰입니다.',
  'coupon.exhausted': '모두 받아 간 쿠폰입니다.',
  'coupon.ended': '기간이 지난 쿠폰입니다.',
  'coupon.not_started': '아직 쓸 수 없는 쿠폰입니다.',
};

export function describeCouponProblem(error: unknown): CouponProblem {
  if (error instanceof NetworkError) return { message: '서버에 닿지 못했습니다. 다시 넣어도 두 번 받지 않습니다.', verify: false };
  if (!(error instanceof ApiError)) return { message: '쿠폰을 처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.', verify: false };
  if (error.status === 403) return { message: '본인인증을 마친 계정만 쿠폰을 받습니다.', verify: true };
  if (error.status === 429) {
    const after = error.retryAfter ? `${Math.ceil(error.retryAfter / 60)}분 뒤에` : '잠시 뒤에';
    return { message: `코드를 너무 자주 틀렸습니다. ${after} 다시 넣어 주세요.`, verify: false };
  }
  const known = error.code ? BY_CODE[error.code] : undefined;
  if (known) return { message: known, verify: false };
  if (error.status === 503) return { message: '결제 서버가 지금 답하지 못합니다. 잠시 뒤에 다시 시도하세요.', verify: false };
  return { message: '쿠폰을 처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.', verify: false };
}
