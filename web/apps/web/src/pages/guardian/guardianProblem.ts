// web/apps/web/src/pages/guardian/guardianProblem.ts
// 보호자 동의의 실패를 화면의 할 일로 바꾼다. 순수한 함수다. 까닭의 이름은 api/guardian.ts 의 머리말을 본다.

import { ApiError, NetworkError } from '../../api/errors';

const UNREACHABLE = '서버에 닿지 못했습니다. 연결을 확인하고 다시 해 주세요.';

export type RequestProblem = {
  message: string;
  /** 보호자 이메일 칸의 글 */
  email?: string;
  /** 내 정보가 달라졌다(본인인증 전, 이미 성년, 보호자가 이미 동의함). 화면이 내 정보를 다시 읽는다 */
  reread: boolean;
};

const REQUEST_MESSAGES: Record<string, string> = {
  identity_verification_required: '본인인증을 먼저 해 주세요.',
  guardian_not_needed: '성년이라 보호자의 동의가 필요 없습니다.',
  guardian_consent_active: '보호자가 이미 동의했습니다. 보호자를 바꾸려면 지금의 보호자가 메일의 링크로 먼저 철회해야 합니다.',
};

/** 미성년자의 요청(POST /guardian/request) */
export function describeRequestProblem(error: unknown): RequestProblem {
  if (error instanceof NetworkError) return { message: UNREACHABLE, reread: false };
  if (!(error instanceof ApiError)) return { message: '보내지 못했습니다. 다시 해 주세요.', reread: false };
  if (error.status === 429) return { message: `보호자에게 너무 자주 보냈습니다. ${error.retryAfter ?? 60}초 뒤에 다시 해 주세요(1분에 1통, 하루 5통).`, reread: false };
  const email = error.fields.guardian_email?.[0];
  if (email) return { message: email, email, reread: false };
  const known = REQUEST_MESSAGES[error.code ?? ''];
  if (known) return { message: known, reread: true };
  return { message: '보내지 못했습니다. 잠시 뒤에 다시 해 주세요.', reread: false };
}

export type LinkProblem = {
  message: string;
  /** 이 링크로는 더 할 수 없다(링크가 틀렸거나 만료, 회원이 이미 성년). 창을 거두고 다시 요청을 받으라고 한다 */
  restart: boolean;
};

export const LINK_INVALID = '링크를 쓸 수 없습니다. 기한(7일)이 지났거나 회원이 다시 요청해 앞의 링크가 바뀌었을 수 있습니다. 회원에게 다시 요청해 달라고 해 주세요.';

const CONSENT_MESSAGES: Record<string, LinkProblem> = {
  guardian_link_invalid: { message: LINK_INVALID, restart: true },
  guardian_not_needed: { message: '회원이 이미 성년이라 동의가 필요 없습니다.', restart: true },
  identity_token_invalid: { message: '본인인증을 처음부터 다시 해 주세요.', restart: false },
  guardian_not_adult: { message: '보호자는 성년(만 19세 이상)이어야 합니다. 보호자 본인의 휴대폰으로 인증해 주세요.', restart: false },
  guardian_is_minor: { message: '회원 본인은 보호자가 될 수 없습니다. 보호자 본인의 휴대폰으로 인증해 주세요.', restart: false },
  identity_unavailable: { message: '지금은 본인인증을 할 수 없습니다. 잠시 뒤에 다시 해 주세요.', restart: false },
};

/** 보호자의 동의(POST /guardian/consent) */
export function describeConsentProblem(error: unknown): LinkProblem {
  if (error instanceof NetworkError) return { message: UNREACHABLE, restart: false };
  if (!(error instanceof ApiError)) return { message: '동의를 적지 못했습니다. 다시 해 주세요.', restart: false };
  return CONSENT_MESSAGES[error.code ?? ''] ?? (error.status === 503 ? (CONSENT_MESSAGES.identity_unavailable as LinkProblem) : { message: '동의를 적지 못했습니다. 잠시 뒤에 다시 해 주세요.', restart: false });
}

/** 보호자의 철회(POST /guardian/revoke) */
export function describeRevokeProblem(error: unknown): LinkProblem {
  if (error instanceof NetworkError) return { message: UNREACHABLE, restart: false };
  if (error instanceof ApiError && error.code === 'guardian_link_invalid') {
    return { message: '링크를 쓸 수 없습니다. 메일에 온 철회 링크를 그대로 열어 주세요.', restart: true };
  }
  return { message: '철회하지 못했습니다. 잠시 뒤에 다시 해 주세요.', restart: false };
}
