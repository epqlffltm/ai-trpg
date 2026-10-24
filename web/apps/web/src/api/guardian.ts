// web/apps/web/src/api/guardian.ts
// 보호자 동의(인증 서버, A4, #336). 미성년자(성년 전)는 보호자가 동의해야 결제할 수 있다. 보호자는 계정을 만들지 않는다.
//   1. 요청: 로그인한 미성년자가 보호자의 이메일을 낸다. 202 이고 그 주소로 동의 링크(GUARDIAN_CONSENT_URL#token=, 7일)가 간다
//   2. 동의: 보호자가 링크의 화면에서 본인인증을 하고 링크의 글자와 본인확인 업체의 글자를 낸다. 로그인하지 않는다
//   3. 철회: 보호자가 메일의 철회 링크(GUARDIAN_REVOKE_URL#token=)의 화면에서 낸다. 두 번 보내도 200 이다
//
// 실패(auth-server/accounts/views.py 의 보호자):
//   - (요청) 400 guardian_email 칸, 403 identity_verification_required, 409 guardian_not_needed·guardian_consent_active,
//     429 guardian_request_unavailable(retry_after)
//   - (동의·철회) 400 guardian_link_invalid: 위조, 만료, 새 요청으로 바뀐 링크를 가르지 않는다
//   - (동의) 400 identity_token_invalid, 403 guardian_not_adult, 409 guardian_not_needed·guardian_is_minor, 503 identity_unavailable

import { apiRequest } from './http';
import type { GuardianRequested, GuardianRevoked } from './types';

const GUARDIAN = '/api/v1/auth/guardian';

/** 보호자에게 동의를 부탁한다. 다시 부탁하면 앞서 보낸 링크는 쓸 수 없다 */
export function requestGuardianConsent(guardianEmail: string): Promise<GuardianRequested> {
  return apiRequest<GuardianRequested>(`${GUARDIAN}/request`, { method: 'POST', body: { guardian_email: guardianEmail } });
}

/** 보호자가 동의한다. 로그인과 상관없다(링크의 서명과 보호자의 본인인증이 확인이다) */
export function giveGuardianConsent(consentToken: string, identityToken: string): Promise<{ detail: string }> {
  return apiRequest(`${GUARDIAN}/consent`, { method: 'POST', body: { consent_token: consentToken, identity_token: identityToken }, skipRefresh: true });
}

/** 보호자가 동의를 철회한다. revoked 는 이번에 철회했는지다 */
export function revokeGuardianConsent(revokeToken: string): Promise<GuardianRevoked> {
  return apiRequest<GuardianRevoked>(`${GUARDIAN}/revoke`, { method: 'POST', body: { revoke_token: revokeToken }, skipRefresh: true });
}
