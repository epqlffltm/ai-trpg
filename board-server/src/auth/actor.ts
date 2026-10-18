// board-server/src/auth/actor.ts

/**
 * 요청한 사람. 서비스가 "누가 하는가"를 받을 때 쓰는 모양이다.
 *
 * 검증한 토큰(AccessClaims)에서 사용자의 ID 와 운영자인지만 꺼낸 것이다. 서비스는 토큰의 나머지를 모른다.
 * 운영자인지는 토큰이 정한다(auth/roles.ts). 서비스는 DB 에 묻지 않는다.
 */

import type { AccessClaims } from './tokens.js';

/** 요청한 사람의 ID(인증 서버의 public_id)와 운영자인지. */
export type Actor = Pick<AccessClaims, 'userId' | 'isOperator'>;
