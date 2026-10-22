// web/apps/web/src/api/account.ts
// 로그인한 본인의 계정(인증 서버). 동의의 상태와 바꾸기, 비밀번호 바꾸기, 모든 기기 로그아웃, 탈퇴 취소.
//
// 다시 동의하거나 탈퇴를 취소해도 지금의 토큰은 그대로 인증 서버에만 통한다.
// 모든 서버에 통하는 토큰은 그 뒤의 /refresh 가 준다(refresh.ts). 동의와 취소의 화면이 마지막에 부른다.

import { apiRequest } from './http';
import { clearSession, storeTokens, type Session } from './session';
import type { ConsentState, ConsentStates, LoginResponse } from './types';

const AUTH = '/api/v1/auth';

/** 항목마다 본인의 동의 상태. 다시 동의할 필수 항목은 pending 이다 */
export async function fetchMyConsents(signal?: AbortSignal): Promise<ConsentState[]> {
  const response = await apiRequest<ConsentStates>(`${AUTH}/me/consents`, signal ? { signal } : {});
  return response.items;
}

/** 그 항목에 동의한다. 화면이 보인 판을 보낸다. 판이 바뀌었으면 409 consent_outdated */
export async function agreeConsent(item: string, version: number): Promise<ConsentState[]> {
  const response = await apiRequest<ConsentStates>(`${AUTH}/me/consents/${encodeURIComponent(item)}`, {
    method: 'PUT',
    body: { version },
  });
  return response.items;
}

/** 그 항목의 동의를 철회한다. 필수 항목은 400 consent_required(철회는 탈퇴다) */
export async function withdrawConsent(item: string): Promise<ConsentState[]> {
  const response = await apiRequest<ConsentStates>(`${AUTH}/me/consents/${encodeURIComponent(item)}`, {
    method: 'DELETE',
  });
  return response.items;
}

/** 비밀번호를 바꾼다. 다른 기기는 로그아웃되고 이 기기는 새 토큰을 받는다 */
export async function changePassword(currentPassword: string, newPassword: string): Promise<Session> {
  const response = await apiRequest<LoginResponse>(`${AUTH}/password/change`, {
    method: 'POST',
    body: { current_password: currentPassword, new_password: newPassword },
  });
  return storeTokens(response);
}

/** 모든 기기에서 로그아웃한다. 이 기기도 끊기므로(세션 버전이 오른다) 화면의 상태도 비운다 */
export async function logoutAll(): Promise<void> {
  await apiRequest<void>(`${AUTH}/logout-all`, { method: 'POST' });
  clearSession();
}

/** 유예 중인 탈퇴를 취소한다. 요청하지 않았어도 200 이다 */
export async function cancelWithdrawal(): Promise<void> {
  await apiRequest<unknown>(`${AUTH}/me/withdrawal`, { method: 'DELETE' });
}

