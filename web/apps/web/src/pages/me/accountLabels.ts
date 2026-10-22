// web/apps/web/src/pages/me/accountLabels.ts
// 마이페이지에 보일 계정 상태의 글. 순수한 함수다.

import type { Me } from '../../api/types';

type Identity = Me['identity'];
type GuardianConsent = Me['guardian_consent'];

const GUARDIAN_LABELS: Record<GuardianConsent, string> = {
  none: '받지 않음',
  requested: '요청함(보호자의 답을 기다리는 중)',
  consented: '받음',
  revoked: '보호자가 철회함',
};

export function identityLabel(identity: Identity): string {
  if (!identity.verified) return '하지 않음';
  if (!identity.legal_adult) return '했음(미성년자)';
  return identity.adult_content ? '했음(성인, 성인용 내용 열림)' : '했음(성인)';
}

export function guardianLabel(consent: GuardianConsent): string {
  return GUARDIAN_LABELS[consent];
}

/** 보호자 동의 줄을 보일까. 본인인증으로 미성년자임을 알았거나 이미 보호자 동의의 기록이 있을 때 */
export function showsGuardian(me: Pick<Me, 'identity' | 'guardian_consent'>): boolean {
  const minor = me.identity.verified && !me.identity.legal_adult;
  return minor || me.guardian_consent !== 'none';
}
