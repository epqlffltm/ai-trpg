// web/apps/web/src/api/signup.ts
// 가입(인증 서버의 세 단계)과 동의 항목. 모두 토큰과 상관이 없어 401 에서 갱신하지 않는다(skipRefresh).
//
//   1. 이메일 → 6자리 코드를 보낸다(새 주소든 이미 가입된 주소든 같은 답이다)
//   2. 코드 → 가입 티켓(30분)
//   3. 티켓과 아이디, 닉네임, 비밀번호, 만 14세 이상, 동의 → 계정. 로그인은 따로 한다

import { apiRequest } from './http';
import type { components } from './generated/auth';

export type ConsentDocument = components['schemas']['ConsentDocument'];
export type SignupProfile = Omit<components['schemas']['SignupCompleteRequest'], 'signup_ticket'>;

const AUTH = '/api/v1/auth';

export function requestSignupCode(email: string): Promise<{ detail: string }> {
  return apiRequest(`${AUTH}/signup`, { method: 'POST', body: { email }, skipRefresh: true });
}

export async function verifySignupCode(email: string, code: string): Promise<string> {
  const response = await apiRequest<components['schemas']['SignupVerified']>(`${AUTH}/signup/verify`, {
    method: 'POST',
    body: { email, code },
    skipRefresh: true,
  });
  return response.signup_ticket;
}

export function completeSignup(signupTicket: string, profile: SignupProfile): Promise<{ detail: string }> {
  return apiRequest(`${AUTH}/signup/complete`, {
    method: 'POST',
    body: { signup_ticket: signupTicket, ...profile },
    skipRefresh: true,
  });
}

/** 동의를 받는 항목마다 지금의 판. 로그인 없이 읽는다 */
export async function fetchConsentDocuments(signal?: AbortSignal): Promise<ConsentDocument[]> {
  const response = await apiRequest<components['schemas']['ConsentDocuments']>(`${AUTH}/consents`, {
    skipRefresh: true,
    ...(signal ? { signal } : {}),
  });
  return response.items;
}
