// web/apps/web/src/api/password.ts
// 비밀번호를 잊었을 때. 메일로 링크(30분, 한 번만)를 받고, 그 링크의 화면에서 새 비밀번호를 정한다.
// 요청은 가입된 주소든 아니든 같은 답이다. 바꾸면 모든 기기가 로그아웃된다.

import { apiRequest } from './http';

const AUTH = '/api/v1/auth';

export function requestPasswordReset(email: string): Promise<{ detail: string }> {
  return apiRequest(`${AUTH}/password/reset`, { method: 'POST', body: { email }, skipRefresh: true });
}

export function confirmPasswordReset(email: string, token: string, newPassword: string): Promise<{ detail: string }> {
  return apiRequest(`${AUTH}/password/reset/confirm`, {
    method: 'POST',
    body: { email, token, new_password: newPassword },
    skipRefresh: true,
  });
}
