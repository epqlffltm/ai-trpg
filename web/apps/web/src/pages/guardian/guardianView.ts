// web/apps/web/src/pages/guardian/guardianView.ts
// 미성년자의 보호자 동의 화면(/me/guardian)이 보일 단계와 입력의 검사. 순수한 함수다.

import type { Me } from '../../api/types';

/** unverified 는 본인인증 전, adult 는 성년이라 동의가 필요 없음. 나머지는 GET /me 의 guardian_consent 그대로 */
export type GuardianStage = 'unverified' | 'adult' | Me['guardian_consent'];

export function guardianStage(me: Pick<Me, 'identity' | 'guardian_consent'>): GuardianStage {
  if (!me.identity.verified) return 'unverified';
  if (me.identity.legal_adult) return 'adult';
  return me.guardian_consent;
}

/** 보호자에게 부탁할 수 있는 단계(보호자가 동의했으면 그 보호자가 먼저 철회해야 한다) */
export function canRequest(stage: GuardianStage): boolean {
  return stage === 'none' || stage === 'requested' || stage === 'revoked';
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** 보호자 이메일의 문제. 없으면 null. 내 이메일은 서버도 막는다(400 guardian_email) */
export function guardianEmailHint(email: string, myEmail: string): string | null {
  const value = email.trim();
  if (value === '') return null;
  if (!EMAIL.test(value)) return '이메일 주소를 확인해 주세요.';
  return value.toLowerCase() === myEmail.trim().toLowerCase() ? '보호자의 이메일을 적어 주세요. 내 이메일은 쓸 수 없습니다.' : null;
}
