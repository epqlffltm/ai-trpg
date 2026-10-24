// web/apps/web/src/pages/guardian/guardianLink.ts
// 보호자의 메일 링크(동의 GUARDIAN_CONSENT_URL#token=, 철회 GUARDIAN_REVOKE_URL#token=)에서 글자를 꺼낸다. 순수한 함수다.
// 인증 서버는 글자를 주소의 # 뒤에 둔다(재설정 링크와 같은 까닭). # 뒤는 서버로 가지 않아 로그에 남지 않는다.

export function parseGuardianLink(hash: string): string | null {
  const params = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash);
  const token = params.get('token');
  return token ? token : null;
}
