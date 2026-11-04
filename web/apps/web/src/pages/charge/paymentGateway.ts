// web/apps/web/src/pages/charge/paymentGateway.ts
// 결제창의 갈래. 결제 서버에 꽂힌 결제 대행사(PAYMENT_PROVIDER)에 맞춰 빌드할 때 고른다(VITE_PAYMENT_GATEWAY).
//
//   - fake(기본): 결제 서버의 가짜 결제 대행사에 맞춘 시험용 결제창. 결제 번호의 앞머리가 결과를 정한다
//     (billing-server/README.md 의 "가짜 결제 대행사가 알아듣는 결제 번호"). 로컬과 CI 의 결제 서버가 가짜다
//   - toss: 토스페이먼츠의 결제창(tossPayment.ts). 클라이언트 키(VITE_TOSS_CLIENT_KEY)가 함께 있어야 한다.
//     API 개별 연동 키의 테스트 키(test_ck_)만 받는다. 자동결제(카드 등록)는 결제위젯 키를 받지 않고,
//     결제 서버도 테스트 키만 받는다(라이브 키는 실제 계약 뒤에 연다). 키가 없거나 모양이 틀리면 none 이다
//   - none: 결제창을 띄우지 않고 준비 중이라 알린다
// 주문과 승인의 흐름(useCharge)은 갈래와 상관없이 같다. 결제창은 마지막에 결제 번호 하나를 넘긴다.
// 결제 서버가 토스인데 화면이 가짜면, 가짜 결제 번호를 서버가 거절한다(돈도 크레딧도 오가지 않는다).

export type GatewayKind = 'fake' | 'toss' | 'none';

/** 받는 클라이언트 키의 모양. API 개별 연동 키의 테스트 키다 */
const TOSS_CLIENT_KEY = /^test_ck_[A-Za-z0-9]+$/;

export function gatewayKind(
  value: string | undefined = import.meta.env.VITE_PAYMENT_GATEWAY as string | undefined,
  clientKey: string | undefined = import.meta.env.VITE_TOSS_CLIENT_KEY as string | undefined,
): GatewayKind {
  if (value === undefined || value === '' || value === 'fake') return 'fake';
  if (value === 'toss' && tossClientKey(clientKey) !== null) return 'toss';
  return 'none';
}

/** 토스페이먼츠의 클라이언트 키. 모양이 틀리면 null 이다 */
export function tossClientKey(
  value: string | undefined = import.meta.env.VITE_TOSS_CLIENT_KEY as string | undefined,
): string | null {
  return value !== undefined && TOSS_CLIENT_KEY.test(value) ? value : null;
}

/** 가짜 결제창에서 고를 결과. prefix 는 결제 번호의 앞머리다 */
export const FAKE_OUTCOMES = [
  { prefix: 'fake_ok_', label: '결제 성공', hint: '승인되어 골드가 들어옵니다.' },
  { prefix: 'fake_declined_', label: '카드 거절', hint: '거절됩니다. 돈은 나가지 않습니다.' },
  { prefix: 'fake_timeout_ok_', label: '답이 오지 않음', hint: '결과를 모르는 채로 끝납니다. 다시 확인하면 승인으로 끝납니다.' },
] as const;

/** 결제마다 다른 가짜 결제 번호. 한 번 쓴 번호는 다른 주문에 다시 쓸 수 없다 */
export function fakePaymentKey(prefix: string, unique: string): string {
  return `${prefix}${unique.replace(/[^A-Za-z0-9_-]/g, '')}`;
}
