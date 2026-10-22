// web/apps/web/src/api/auth.ts
// 인증 서버(/api/v1/auth/)를 부르는 것. 로그인 두 단계, 코드 다시 받기, 로그아웃, 내 계정.
// 로그인의 요청은 토큰과 상관이 없어서 401 에서 갱신하지 않는다(skipRefresh).

import { NetworkError } from './errors';
import { apiRequest } from './http';
import { clearSession, storeTokens, type Session } from './session';
import type { LoginChallenge, LoginResponse, Me } from './types';

const AUTH = '/api/v1/auth';

/** 로그인 1단계. 아이디와 비밀번호가 맞으면 메일로 코드가 가고 티켓이 온다 */
export function startLogin(username: string, password: string): Promise<LoginChallenge> {
  return apiRequest<LoginChallenge>(`${AUTH}/login`, {
    method: 'POST',
    body: { username, password },
    skipRefresh: true,
  });
}

/** 로그인 2단계. 코드가 맞으면 토큰을 받아 지금의 상태로 둔다. refresh 쿠키는 서버가 심는다 */
export async function verifyLogin(loginTicket: string, code: string): Promise<Session> {
  const response = await apiRequest<LoginResponse>(`${AUTH}/login/verify`, {
    method: 'POST',
    body: { login_ticket: loginTicket, code },
    skipRefresh: true,
  });
  return storeTokens(response);
}

export function resendLoginCode(loginTicket: string): Promise<{ detail: string }> {
  return apiRequest<{ detail: string }>(`${AUTH}/login/resend`, {
    method: 'POST',
    body: { login_ticket: loginTicket },
    skipRefresh: true,
  });
}

/**
 * 이 기기에서 로그아웃한다. 서버가 refresh 토큰을 폐기하고 쿠키를 지운다.
 * 서버에 닿지 못해도 화면의 상태는 비운다. 쿠키는 남지만 다음 갱신이 이 기기의 로그인을 되살릴 뿐이다
 */
export async function logout(): Promise<void> {
  try {
    await apiRequest<void>(`${AUTH}/logout`, { method: 'POST', skipRefresh: true });
  } catch (error) {
    if (!(error instanceof NetworkError)) throw error;
  } finally {
    clearSession();
  }
}

export function fetchMe(signal?: AbortSignal): Promise<Me> {
  return apiRequest<Me>(`${AUTH}/me`, signal ? { signal } : {});
}
