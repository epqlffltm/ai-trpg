// web/apps/web/src/pages/orders/refundProblem.ts
// 청약철회의 실패를 화면의 할 일로. 순수한 함수다(billing-server/README.md 의 "청약철회").
//   - 답을 받지 못함, 5xx: 다시 보낸다. 같은 취소는 한 번만 된다(retry)
//   - 409: code 가 까닭이다. 엇갈림(refund.busy)만 다시 보내면 되고, 나머지는 주문을 다시 읽어 지금 상태를 보인다(refresh)
//   - 404: 없는 주문이거나 남의 주문이다
//   - 403 step_up.required: 본인 확인 창을 닫았다(확인하면 다시 보낸다, stepUpGate.ts). 다시 누르면 또 묻는다
//   - 403 step_up.disabled: 본인 확인을 끈 계정이다. 마이페이지에서 다시 켜면 확인을 받고 할 수 있다

import { ApiError, NetworkError } from '../../api/errors';
import type { FormProblem } from '../../auth/problem';
import { refusalRetryable, refusedText } from './orderView';

export const STEP_UP_REQUIRED = '본인 확인을 마쳐야 청약철회할 수 있습니다. 다시 누르면 확인 코드를 보냅니다.';
export const STEP_UP_DISABLED =
  '본인 확인을 끈 계정은 청약철회를 할 수 없습니다. 마이페이지의 내 계정에서 본인 확인을 다시 켜고 해 주세요.';

export type RefundProblem = FormProblem & { retry: boolean; refresh: boolean };

export function describeRefundProblem(error: unknown): RefundProblem {
  if (error instanceof NetworkError || (error instanceof ApiError && error.status >= 500)) {
    return { message: '서버가 답하지 못했습니다. 다시 보내도 환불은 한 번만 됩니다.', retry: true, refresh: false };
  }
  if (!(error instanceof ApiError)) return { message: '환불하지 못했습니다.', retry: false, refresh: true };
  if (error.status === 409) return { message: refusedText(error.code), retry: refusalRetryable(error.code), refresh: true };
  if (error.status === 404) return { message: '그런 주문이 없습니다.', retry: false, refresh: true };
  if (error.code === 'step_up.required') return { message: STEP_UP_REQUIRED, retry: true, refresh: false };
  if (error.code === 'step_up.disabled') return { message: STEP_UP_DISABLED, retry: false, refresh: false };
  return { message: '환불하지 못했습니다.', retry: false, refresh: true };
}
