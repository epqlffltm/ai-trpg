// web/apps/web/src/auth/roles.ts
// access 토큰에 실린 역할(roles)을 읽는다. 운영자의 화면(E4)을 보일지 정하는 데만 쓴다.
//
// 서명은 확인하지 않는다. 화면이 메뉴와 경로를 숨기는 것일 뿐, 권한은 서버가 정한다(운영자가 아니면 /admin API 가 404).
// 인증 서버가 운영자의 토큰에 roles: ["operator"] 를 싣는다(auth-server/accounts/tokens.py, docs/architecture/operators.md).

import type { Session } from '../api/session';

const OPERATOR_ROLE = 'operator';

/** 토큰의 가운데 조각(payload)을 JSON 으로 읽는다. 모양이 틀리면 null */
export function tokenClaims(token: string): Record<string, unknown> | null {
  const payload = token.split('.')[1];
  if (!payload) return null;
  try {
    const parsed: unknown = JSON.parse(decodeBase64Url(payload));
    return parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** base64url 을 UTF-8 글로 푼다 */
export function decodeBase64Url(text: string): string {
  const base64 = text.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(text.length / 4) * 4, '=');
  const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

/** 토큰의 역할들. 없거나 읽지 못하면 빈 목록 */
export function rolesOf(token: string): string[] {
  const roles = tokenClaims(token)?.roles;
  return Array.isArray(roles) ? roles.filter((role): role is string => typeof role === 'string') : [];
}

/** 운영자로 로그인했는가 */
export function isOperator(session: Session | null): boolean {
  return session !== null && rolesOf(session.accessToken).includes(OPERATOR_ROLE);
}
