// web/apps/web/src/pages/charge/chargeProblem.ts
// 주문 만들기와 승인 요청의 실패를 화면의 할 일로 바꾼다. 순수한 함수다.
// 결제 서버의 답(billing-server/README.md 의 "주문과 결제"):
//   - 답을 받지 못함, 503, 5xx: 결제를 실패로 정한 것이 아니다. 같은 열쇠(주문)나 같은 결제 번호(승인)로 다시 보낸다(retry)
//   - 403 payment.verification_required: 본인인증을 해야 한다. 403 payment.guardian_consent_required: 보호자 동의가 있어야 한다
//   - 409: 같은 열쇠로 다른 상품, 주문이 만료됨, 다른 결제 번호로 이미 진행됨. 다시 보내도 같다. 처음부터 다시(restart)
//   - 400, 404: 주문이나 결제 번호가 맞지 않다. 처음부터 다시

import { ApiError, NetworkError } from '../../api/errors';

export type ChargeProblem = {
  message: string;
  /** 같은 것을 다시 보내면 될 수 있다(열쇠와 결제 번호를 그대로 둔다) */
  retry: boolean;
  /** 처음(상품 고르기)부터 다시 */
  restart: boolean;
};

const RETRY_ORDER = '결제 서버에 닿지 못했습니다. 다시 보내도 주문은 하나만 생깁니다.';
const RETRY_CONFIRM = '결제 서버가 답하지 못했습니다. 결제가 실패한 것이 아닙니다. 다시 확인해 주세요.';

const FORBIDDEN: Record<string, string> = {
  'payment.verification_required': '본인인증을 마친 계정만 충전할 수 있습니다. 내 정보 → 본인인증에서 먼저 해 주세요.',
  'payment.guardian_consent_required': '만 19세 미만은 보호자가 동의해야 충전할 수 있습니다. 보호자 동의 화면은 준비 중입니다.',
};

function retryable(error: unknown): boolean {
  if (error instanceof NetworkError) return true;
  return error instanceof ApiError && error.status >= 500;
}

/** stage 는 어느 걸음에서 났는가. 다시 보내라는 말이 걸음마다 다르다 */
export function describeChargeProblem(error: unknown, stage: 'order' | 'confirm'): ChargeProblem {
  if (retryable(error)) return { message: stage === 'order' ? RETRY_ORDER : RETRY_CONFIRM, retry: true, restart: false };
  if (!(error instanceof ApiError)) return { message: '처리하지 못했습니다. 처음부터 다시 해 주세요.', retry: false, restart: true };
  if (error.status === 403) {
    return { message: FORBIDDEN[error.code ?? ''] ?? '지금은 충전할 수 없는 계정입니다.', retry: false, restart: true };
  }
  if (error.status === 409) {
    const message = stage === 'order' ? '주문을 만들지 못했습니다. 상품을 다시 골라 주세요.' : '이 주문은 더 진행할 수 없습니다(시간이 지났거나 이미 다른 결제로 진행됨). 처음부터 다시 해 주세요.';
    return { message, retry: false, restart: true };
  }
  return { message: '주문이나 결제 정보가 맞지 않습니다. 처음부터 다시 해 주세요.', retry: false, restart: true };
}
