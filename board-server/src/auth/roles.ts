// board-server/src/auth/roles.ts

/**
 * access 토큰의 역할(roles)을 읽는다(#389, docs/architecture/operators.md). Nest 도 DB 도 모른다.
 *
 * 누가 운영자인지는 인증 서버가 정한다(Django 그룹 operators). 인증 서버는 access 토큰을 만들 때
 * 운영자면 roles 에 ["operator"] 를, 아니면 [] 를 싣는다. 게임 서버(app/auth/tokens.py)와 같은 규칙으로 읽는다.
 *
 *   - 목록에 "operator" 가 정확히 있을 때만 운영자다.
 *   - 목록이 아니면(글자 "operator" 하나, 객체) 운영자가 아니다. 토큰을 거부하지는 않는다.
 *   - 모르는 역할은 무시한다. 인증 서버가 역할을 더해도 이 서버가 깨지지 않는다.
 *   - 없으면 운영자가 아니다. 이 클레임이 생기기 전에 발급한 토큰이 있다.
 */

/** 역할의 목록이 적힌 칸. 인증 서버의 accounts/tokens.py 의 ROLES_CLAIM 과 같다 */
export const ROLES_CLAIM = 'roles';
/** 운영자의 역할 이름. 인증 서버의 accounts/roles.py 의 OPERATOR_ROLE 과 같다 */
export const OPERATOR_ROLE = 'operator';

/** 토큰의 roles 칸이 운영자라고 적었는가. */
export function readIsOperator(roles: unknown): boolean {
  return Array.isArray(roles) && roles.includes(OPERATOR_ROLE);
}
