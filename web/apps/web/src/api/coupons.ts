// web/apps/web/src/api/coupons.ts
// 쿠폰(결제 서버, #979). 코드를 넣어 실버를 받는다.
//
// 실패(billing-server/README.md 의 "쿠폰"):
//   - 403 coupon.verification_required: 본인인증 전이다
//   - 404 coupon.not_found: 그런 코드가 없다. 틀린 시도로 센다
//   - 409 coupon.already_redeemed, coupon.exhausted, coupon.ended, coupon.not_started
//   - 429 coupon.too_many_attempts: 한 시간에 열 번 넘게 틀렸다. Retry-After 의 초 뒤에 다시 넣는다
// 한 사람은 한 쿠폰을 한 번만 받는다. 다시 보내도 두 번 받지 않는다(두 번째는 409). 그래서 열쇠를 붙이지 않는다.

import { apiRequest } from './http';
import type { CouponRedemption } from './types';

/** 코드를 넣어 실버를 받는다. 서버가 앞뒤 빈칸을 지우고 대문자로 바꿔 찾는다 */
export function redeemCoupon(code: string): Promise<CouponRedemption> {
  return apiRequest<CouponRedemption>('/api/v1/billing/coupons/redeem', { method: 'POST', body: { code } });
}
