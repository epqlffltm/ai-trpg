// web/apps/web/src/api/identity.ts
// 휴대폰 본인인증(인증 서버, A3, #336). 본인확인 업체의 화면에서 받은 글자(token)를 낸다. 모양은 업체가 정한다.
//
// 실패(auth-server/accounts/views.py 의 본인인증):
//   - 400 identity_token_invalid: 업체가 그 글자를 모른다. 업체 화면부터 다시
//   - 403 identity_under_age: 만 14세 미만이라 계정을 막았다. refresh 쿠키도 지운다(로그인이 끝난다)
//   - 403 identity_blocked: 정지된 채 탈퇴한 사람이라 인증하지 않았다
//   - 409 identity_already_verified, identity_in_use: 이미 인증했다, 다른 계정이 그 사람으로 인증했다
//   - 503 identity_unavailable: 본인인증을 받지 않는 서버이거나 업체가 답하지 않는다

import { apiRequest } from './http';
import type { IdentityAnswer } from './types';

/** 본인인증을 마친다. 답은 바뀐 본인인증 상태다. 성인용을 보려면 그 뒤에 토큰을 한 번 갱신한다 */
export function verifyIdentity(token: string): Promise<IdentityAnswer> {
  return apiRequest<IdentityAnswer>('/api/v1/auth/identity/verify', { method: 'POST', body: { token } });
}
