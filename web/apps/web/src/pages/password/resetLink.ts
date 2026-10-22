// web/apps/web/src/pages/password/resetLink.ts
// 재설정 메일의 링크에서 이메일과 토큰을 꺼낸다. 순수한 함수다.
// 인증 서버는 둘을 주소의 # 뒤에 둔다(PASSWORD_RESET_URL#email=...&token=...). # 뒤는 서버로 가지 않아 로그에 남지 않는다.

export type ResetLink = { email: string; token: string };

export function parseResetLink(hash: string): ResetLink | null {
  const params = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash);
  const email = params.get('email');
  const token = params.get('token');
  return email && token ? { email, token } : null;
}
