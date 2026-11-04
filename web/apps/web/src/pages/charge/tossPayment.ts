// web/apps/web/src/pages/charge/tossPayment.ts
// 토스페이먼츠의 결제창(VITE_PAYMENT_GATEWAY=toss). 결제창을 열고(openTossPayment), 돌아온 주소를 읽는다(readChargeReturn).
//
// 결제창은 현재 창에서 연다(windowTarget 'self'). 결제를 마치면 토스페이먼츠가 돌아오는 주소(CHARGE_RETURN_PATH)로 보낸다.
//   - 성공: ?paymentKey=&orderId=&amount=  화면이 결제 번호로 승인을 요청한다(useChargeReturn). 승인은 결제 서버가 한다
//   - 실패: ?code=&message=&orderId=       화면은 code 만 읽는다. message 는 주소에 실려 오므로 누구나 꾸밀 수 있다
// PC 에서도 새 창이나 iframe 을 쓰지 않는다. 모바일과 앱(WebView)이 같은 길로 가고, 화면의 CSP 는 SDK 의 스크립트만 열면 된다
// (docker/nginx/templates/web-headers.inc.template).
// 금액은 결제 서버가 주문에서 찾아 토스페이먼츠에 보낸다. 돌아온 주소의 amount 가 다르면 토스페이먼츠가 승인하지 않는다.
// SDK 는 처음 결제창을 열 때 받는다(loadTossPayments 가 js.tosspayments.com 에서 스크립트를 받는다). 다른 화면은 받지 않는다.

import { ANONYMOUS, loadTossPayments } from '@tosspayments/tosspayments-sdk';
import type { Order } from '../../api/types';
import { goldLabel } from './chargeView';

/** 결제창이 돌아오는 화면. 성공과 실패가 같은 곳으로 온다 */
export const CHARGE_RETURN_PATH = '/wallet/charge/return';

/** 결제창에 넘기는 것. 카드 결제, 원화, 주문 번호는 결제 서버의 주문 번호다 */
export function chargeRequest(order: Order, origin: string) {
  const returnUrl = origin + CHARGE_RETURN_PATH;
  return {
    method: 'CARD' as const,
    amount: { currency: 'KRW', value: order.price },
    orderId: order.id,
    orderName: goldLabel(order.credits),
    successUrl: returnUrl,
    failUrl: returnUrl,
    windowTarget: 'self' as const,
  };
}

/** 토스페이먼츠의 결제창을 연다. 열리면 이 페이지를 떠난다. 열지 못했거나 사용자가 닫았으면 오류다 */
export async function openTossPayment(clientKey: string, order: Order, origin: string = window.location.origin): Promise<void> {
  const tossPayments = await loadTossPayments(clientKey);
  // 결제창의 카드 결제는 구매자를 묻지 않는다. 자동결제(카드 등록)는 결제 서버가 준 고객 키를 쓴다
  await tossPayments.payment({ customerKey: ANONYMOUS }).requestPayment(chargeRequest(order, origin));
}

/** 사용자가 결제창을 닫은 것인지. 그때는 오류를 보이지 않는다 */
export function closedByUser(error: unknown): boolean {
  const code = (error as { code?: unknown } | null)?.code;
  return code === 'USER_CANCEL' || code === 'PAY_PROCESS_CANCELED';
}

export type ChargeReturn =
  | { kind: 'paid'; orderId: string; paymentKey: string }
  | { kind: 'failed'; code: string | null }
  | { kind: 'unreadable' };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const PAYMENT_KEY = /^[A-Za-z0-9_-]{1,200}$/;
const CODE = /^[A-Z0-9_]{1,64}$/;

/** 돌아온 주소를 읽는다. 결제 번호와 주문 번호의 모양이 틀리면 읽지 않는다(서버에 보내지 않는다) */
export function readChargeReturn(search: URLSearchParams): ChargeReturn {
  const paymentKey = search.get('paymentKey');
  const orderId = search.get('orderId');
  if (paymentKey !== null) {
    if (orderId === null || !UUID.test(orderId) || !PAYMENT_KEY.test(paymentKey)) return { kind: 'unreadable' };
    return { kind: 'paid', orderId, paymentKey };
  }
  const code = search.get('code');
  if (code !== null) return { kind: 'failed', code: CODE.test(code) ? code : null };
  return { kind: 'unreadable' };
}

/** 결제창이 실패로 돌려보낸 까닭. 모르는 것은 한 말로 */
const RETURN_FAILURES: Record<string, string> = {
  PAY_PROCESS_CANCELED: '결제를 그만두었습니다. 돈은 나가지 않았습니다.',
  PAY_PROCESS_ABORTED: '결제가 중간에 끊겼습니다. 돈은 나가지 않았습니다. 다시 해 주세요.',
  REJECT_CARD_COMPANY: '카드사가 결제를 거절했습니다. 다른 카드로 해 주세요.',
};

export function returnFailureText(code: string | null): string {
  return (code ? RETURN_FAILURES[code] : undefined) ?? '결제하지 못했습니다. 돈은 나가지 않았습니다. 다시 해 주세요.';
}
