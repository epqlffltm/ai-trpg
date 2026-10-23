// web/apps/web/src/pages/wallet/walletProblem.ts
// 지갑을 읽지 못한 까닭을 화면의 한 줄로. 순수한 함수다.
// 결제 서버의 503 은 잠시 뒤 다시 부를 것이다(DB 의 시간 제한, 공개키를 구할 수 없음). 로그아웃시키지 않는다.
// 401 은 http.ts 가 갱신을 한 번 해 보고, 그래도 401 이면 로그인 화면으로 가는 것은 RequireSession 이 맡는다.

import { ApiError, NetworkError } from '../../api/errors';

export function walletProblemText(error: unknown): string {
  if (error instanceof NetworkError) return '서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요.';
  if (error instanceof ApiError && error.status === 503) {
    const after = error.retryAfter ? ` ${error.retryAfter}초 뒤에` : ' 잠시 뒤에';
    return `결제 서버가 지금 답하지 못합니다.${after} 다시 시도하세요.`;
  }
  return '지갑을 불러오지 못했습니다. 잠시 뒤에 다시 시도하세요.';
}
