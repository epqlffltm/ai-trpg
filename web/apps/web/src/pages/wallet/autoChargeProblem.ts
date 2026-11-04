// web/apps/web/src/pages/wallet/autoChargeProblem.ts
// 자동 충전(#980)의 설정과 카드 등록이 되지 않은 까닭을 화면의 한 줄로. 순수한 함수다. 까닭은 결제 서버의 code 다(api/autoCharge.ts).
// 결제할 수 없는 계정이면 화면이 본인인증이나 보호자 동의로 가는 길을 붙인다(link).

import { ApiError, NetworkError } from '../../api/errors';

export type AutoChargeProblem = { message: string; link: { to: string; label: string } | null };

const BY_CODE: Record<string, AutoChargeProblem> = {
  'autocharge.no_card': { message: '자동 충전을 켜려면 먼저 카드를 등록해 주세요.', link: null },
  'autocharge.invalid_settings': { message: '설정의 값이 맞지 않습니다. 다시 확인해 주세요.', link: null },
  'payment.verification_required': {
    message: '본인인증을 마친 계정만 자동 충전을 켤 수 있습니다.',
    link: { to: '/me/identity', label: '본인인증하기' },
  },
  'payment.guardian_consent_required': {
    message: '만 19세 미만은 보호자가 동의해야 자동 충전을 켤 수 있습니다.',
    link: { to: '/me/guardian', label: '보호자 동의 부탁하기' },
  },
  'card.invalid_request': { message: '카드를 등록하지 못했습니다. 처음부터 다시 해 주세요.', link: null },
  'card.customer_key_mismatch': { message: '카드 등록을 처음부터 다시 해 주세요.', link: null },
  'card.refused': { message: '카드를 등록하지 못했습니다. 다른 카드로 해 주세요.', link: null },
  'card.issuer_unavailable': { message: '결제 대행사가 답하지 않았습니다. 다시 등록해 주세요.', link: null },
};

const UNKNOWN: AutoChargeProblem = { message: '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.', link: null };

export function describeAutoChargeProblem(error: unknown): AutoChargeProblem {
  if (error instanceof NetworkError) return { message: '결제 서버에 닿지 못했습니다. 다시 시도하세요.', link: null };
  if (!(error instanceof ApiError)) return UNKNOWN;
  const known = error.code ? BY_CODE[error.code] : undefined;
  if (known) return known;
  if (error.status === 503) return { message: '결제 서버가 지금 답하지 못합니다. 잠시 뒤에 다시 시도하세요.', link: null };
  return UNKNOWN;
}
