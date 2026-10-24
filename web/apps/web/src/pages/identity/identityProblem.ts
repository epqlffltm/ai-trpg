// web/apps/web/src/pages/identity/identityProblem.ts
// 본인인증의 실패를 화면의 할 일로 바꾼다. 순수한 함수다. 까닭의 이름은 api/identity.ts 의 머리말을 본다.

import { ApiError, NetworkError } from '../../api/errors';

export type IdentityProblem = {
  message: string;
  /** 계정이 막혀 로그인이 끝났다(만 14세 미만). 화면이 상태를 비우고 로그인 화면으로 보낸다 */
  signedOut: boolean;
  /** 이미 인증했다. 화면이 내 정보를 다시 읽는다 */
  verified: boolean;
};

export const UNDER_AGE = '만 14세 미만은 이용할 수 없어 계정을 막았습니다. 가입 때 받은 정보는 지웠습니다.';

const MESSAGES: Record<string, string> = {
  identity_token_invalid: '본인인증을 처음부터 다시 해 주세요.',
  identity_blocked: '이 사람으로는 본인인증을 할 수 없습니다. 문의해 주세요.',
  identity_already_verified: '이미 본인인증을 마친 계정입니다.',
  identity_in_use: '다른 계정이 이미 이 사람으로 본인인증을 했습니다. 한 사람은 한 계정만 씁니다. 문의해 주세요.',
  identity_unavailable: '지금은 본인인증을 할 수 없습니다. 잠시 뒤에 다시 해 주세요.',
};

export function describeIdentityProblem(error: unknown): IdentityProblem {
  const base = { signedOut: false, verified: false };
  if (error instanceof NetworkError) return { ...base, message: '서버에 닿지 못했습니다. 연결을 확인하고 다시 해 주세요.' };
  if (!(error instanceof ApiError)) return { ...base, message: '본인인증을 마치지 못했습니다. 다시 해 주세요.' };
  if (error.code === 'identity_under_age') return { message: UNDER_AGE, signedOut: true, verified: false };
  const message = MESSAGES[error.code ?? ''] ?? (error.status === 503 ? MESSAGES.identity_unavailable : '본인인증을 마치지 못했습니다. 다시 해 주세요.');
  return { message: message ?? '', signedOut: false, verified: error.code === 'identity_already_verified' };
}
