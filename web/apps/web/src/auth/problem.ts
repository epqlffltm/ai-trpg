// web/apps/web/src/auth/problem.ts
// 인증 화면(로그인, 가입, 비밀번호)의 실패를 화면에 보일 모양(FormProblem)과 화면마다 같은 부분.
// 화면마다 다른 것(401 의 뜻, 처음부터 다시 할 때)은 loginProblem.ts, signupProblem.ts, passwordProblem.ts 가 정한다.
// 로그인을 확인하지 못한 503(auth_unavailable)의 글도 여기 둔다. 서비스마다의 실패 글이 503 을 그 서버의 탓으로 적기 전에 먼저 본다.

import { ApiError, isNetworkBlocked, NetworkError } from '../api/errors';

export type FormProblem = {
  message: string;
  /** 이만큼(초) 기다린 뒤에 다시 누를 수 있다 */
  waitSeconds?: number;
  /** 티켓이나 링크를 더 쓸 수 없어 처음부터 다시 해야 한다 */
  restart?: boolean;
  /** 칸마다의 문제(형식이 틀린 입력, 이미 쓰는 이름) */
  fields?: Record<string, string>;
  /** 문의할 때 알려 줄 요청의 번호 */
  requestId?: string;
};

export const UNREACHABLE = '서버에 닿지 못했습니다. 잠시 뒤에 다시 시도하세요.';
export const UNKNOWN = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
export const NETWORK_BLOCKED = '이 네트워크에서는 가입과 로그인이 제한되었습니다. 잘못 막혔다면 고객 문의로 알려 주세요.';

/**
 * 서버가 토큰을 확인하지 못했다(503, code auth_unavailable). 인증 서버가 꺼져 공개키를 구할 수 없다.
 * 부른 서버(결제, 게시판 …)는 멀쩡하다. 그 서버의 탓으로 적지 않는다. 로그아웃시키지 않는다
 */
export const AUTH_UNAVAILABLE = 'auth_unavailable';

/** 로그인을 확인하지 못한 503 이면 그 글. 아니면 null */
export function authUnavailableText(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.status !== 503 || error.code !== AUTH_UNAVAILABLE) return null;
  const after = error.retryAfter ? `${error.retryAfter}초 뒤에` : '잠시 뒤에';
  return `지금은 로그인을 확인할 수 없습니다. ${after} 다시 시도하세요.`;
}

/** 화면마다 같은 실패: 서버에 닿지 못함, 모르는 오류, 너무 많은 시도(429), 막은 IP(403 network_blocked, #638),
 * 로그인을 확인하지 못함(503 auth_unavailable). 아니면 null */
export function commonProblem(error: unknown): FormProblem | null {
  if (error instanceof NetworkError) return { message: UNREACHABLE };
  if (!(error instanceof ApiError)) return { message: UNKNOWN };
  if (error.status === 429) return tooMany(error);
  if (isNetworkBlocked(error)) return unknownProblem(error, NETWORK_BLOCKED);
  const auth = authUnavailableText(error);
  if (auth) return { message: auth };
  return null;
}

/** 메일 코드를 너무 자주 받으려 했다는 까닭(로그인 코드, 본인 확인 코드) */
const CODE_REQUEST_LIMITS = new Set(['login_code_unavailable', 'step_up_code_unavailable']);

function tooMany(error: ApiError): FormProblem {
  const seconds = error.retryAfter ?? 60;
  const what = CODE_REQUEST_LIMITS.has(error.code ?? '') ? '코드를 너무 자주 요청했습니다.' : '시도가 너무 많습니다.';
  return { message: `${what} ${seconds}초 뒤에 다시 시도하세요.`, waitSeconds: seconds };
}

/** 모르는 실패. 문의할 때 쓸 요청 번호를 붙인다 */
export function unknownProblem(error: ApiError, message = UNKNOWN): FormProblem {
  return error.requestId ? { message, requestId: error.requestId } : { message };
}

/** 칸마다 첫 글 하나. 칸을 가르지 않는 오류(non_field_errors)는 칸이 아니라 message 로 쓴다 */
export function fieldProblem(error: ApiError, fallback: string): FormProblem {
  const fields: Record<string, string> = {};
  for (const [name, messages] of Object.entries(error.fields)) {
    if (name !== 'non_field_errors' && messages[0]) fields[name] = messages[0];
  }
  const message = error.fields.non_field_errors?.[0] ?? fallback;
  return { message, fields };
}
