// web/apps/web/src/pages/orders/refundProblem.ts
// 청약철회의 실패를 화면의 할 일로. 순수한 함수다(billing-server/README.md 의 "청약철회").
//   - 답을 받지 못함, 5xx: 다시 보낸다. 같은 취소는 한 번만 된다(retry)
//   - 409: code 가 까닭이다. 엇갈림(refund.busy)만 다시 보내면 되고, 나머지는 주문을 다시 읽어 지금 상태를 보인다(refresh)
//   - 404: 없는 주문이거나 남의 주문이다

import { ApiError, NetworkError } from '../../api/errors';
import type { FormProblem } from '../../auth/problem';
import { refusalRetryable, refusedText } from './orderView';

export type RefundProblem = FormProblem & { retry: boolean; refresh: boolean };

export function describeRefundProblem(error: unknown): RefundProblem {
  if (error instanceof NetworkError || (error instanceof ApiError && error.status >= 500)) {
    return { message: '서버가 답하지 못했습니다. 다시 보내도 환불은 한 번만 됩니다.', retry: true, refresh: false };
  }
  if (!(error instanceof ApiError)) return { message: '환불하지 못했습니다.', retry: false, refresh: true };
  if (error.status === 409) return { message: refusedText(error.code), retry: refusalRetryable(error.code), refresh: true };
  if (error.status === 404) return { message: '그런 주문이 없습니다.', retry: false, refresh: true };
  return { message: '환불하지 못했습니다.', retry: false, refresh: true };
}
