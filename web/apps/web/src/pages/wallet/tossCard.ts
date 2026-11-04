// web/apps/web/src/pages/wallet/tossCard.ts
// 토스페이먼츠의 카드 등록 창(자동결제, #980). 창을 열고(openTossCardRegistration), 돌아온 주소를 읽는다(readCardReturn).
//
// 등록 창은 결제창(charge/tossPayment.ts)처럼 현재 창에서 연다(windowTarget 'self'). 마치면 돌아오는 화면(CARD_RETURN_PATH)으로 온다.
//   - 성공: ?customerKey=&authKey=  화면이 인증 키와 고객 키로 카드를 등록한다(useCardReturn). 빌링키는 결제 서버가 받는다
//   - 실패: ?code=&message=         화면은 code 만 읽는다. message 는 주소에 실려 오므로 누구나 꾸밀 수 있다
// 고객 키는 결제 서버가 준다(createCustomerKey). 서버는 등록할 때 그 키가 이 사람의 것인지 본다.

import { loadTossPayments } from '@tosspayments/tosspayments-sdk';

/** 카드 등록 창이 돌아오는 화면. 성공과 실패가 같은 곳으로 온다 */
export const CARD_RETURN_PATH = '/wallet/card/return';

/** 카드 등록 창에 넘기는 것. 카드, 같은 화면으로 돌아오기, 현재 창 */
export function cardRegistrationRequest(origin: string) {
  const returnUrl = origin + CARD_RETURN_PATH;
  return { method: 'CARD' as const, successUrl: returnUrl, failUrl: returnUrl, windowTarget: 'self' as const };
}

/** 토스페이먼츠의 카드 등록 창을 연다. 열리면 이 페이지를 떠난다. 열지 못했거나 사용자가 닫았으면 오류다 */
export async function openTossCardRegistration(
  clientKey: string,
  customerKey: string,
  origin: string = window.location.origin,
): Promise<void> {
  const tossPayments = await loadTossPayments(clientKey);
  await tossPayments.payment({ customerKey }).requestBillingAuth(cardRegistrationRequest(origin));
}

export type CardReturn =
  | { kind: 'registered'; authKey: string; customerKey: string }
  | { kind: 'failed'; code: string | null }
  | { kind: 'unreadable' };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
/** 인증 키의 모양. 결제 서버도 길이를 본다(autocharge.CheckAuthKey) */
const AUTH_KEY = /^[A-Za-z0-9_-]{1,300}$/;
const CODE = /^[A-Z0-9_]{1,64}$/;

/** 돌아온 주소를 읽는다. 인증 키와 고객 키의 모양이 틀리면 읽지 않는다(서버에 보내지 않는다) */
export function readCardReturn(search: URLSearchParams): CardReturn {
  const authKey = search.get('authKey');
  const customerKey = search.get('customerKey');
  if (authKey !== null) {
    if (customerKey === null || !UUID.test(customerKey) || !AUTH_KEY.test(authKey)) return { kind: 'unreadable' };
    return { kind: 'registered', authKey, customerKey };
  }
  const code = search.get('code');
  if (code !== null) return { kind: 'failed', code: CODE.test(code) ? code : null };
  return { kind: 'unreadable' };
}

/** 등록 창이 실패로 돌려보낸 까닭. 모르는 것은 한 말로 */
const RETURN_FAILURES: Record<string, string> = {
  PAY_PROCESS_CANCELED: '카드 등록을 그만두었습니다.',
  USER_CANCEL: '카드 등록을 그만두었습니다.',
  REJECT_CARD_COMPANY: '카드사가 등록을 거절했습니다. 다른 카드로 해 주세요.',
};

export function cardReturnFailureText(code: string | null): string {
  return (code ? RETURN_FAILURES[code] : undefined) ?? '카드를 등록하지 못했습니다. 다시 해 주세요.';
}
