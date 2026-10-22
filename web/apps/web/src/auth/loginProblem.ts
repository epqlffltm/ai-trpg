// web/apps/web/src/auth/loginProblem.ts
// 로그인의 실패를 화면에 보일 것으로 바꾼다(화면 명세 A2 의 "버튼이 비활성인 조건"). 화면을 그리지 않는 순수한 함수다.
//
// 아이디가 없는 것과 비밀번호가 틀린 것, 정지된 계정을 가르지 않는다. 서버도 같은 401 을 준다.

import { ApiError, NetworkError } from '../api/errors';

export type LoginStep = 'credentials' | 'code';

export type LoginProblem = {
  message: string;
  /** 이만큼(초) 기다린 뒤에 다시 누를 수 있다 */
  waitSeconds?: number;
  /** 티켓을 더 쓸 수 없어 1단계부터 다시 해야 한다 */
  restart?: boolean;
  /** 칸마다의 문제(형식이 틀린 입력) */
  fields?: Record<string, string>;
  /** 문의할 때 알려 줄 요청의 번호 */
  requestId?: string;
};

const WRONG_CREDENTIALS = '아이디 또는 비밀번호가 맞지 않습니다. 계속 안 되면 문의해 주세요.';
const NOT_VERIFIED = '가입할 때 받은 메일의 인증을 아직 마치지 않았습니다. 가입을 처음부터 다시 진행해 주세요.';
const TICKET_GONE = '로그인 시간이 지났습니다. 아이디와 비밀번호부터 다시 입력해 주세요.';
const UNREACHABLE = '서버에 닿지 못했습니다. 잠시 뒤에 다시 시도하세요.';
const UNKNOWN = '로그인하지 못했습니다. 잠시 뒤에 다시 시도하세요.';

export function describeLoginProblem(error: unknown, step: LoginStep): LoginProblem {
  if (error instanceof NetworkError) return { message: UNREACHABLE };
  if (!(error instanceof ApiError)) return { message: UNKNOWN };
  if (error.status === 429) return tooMany(error);
  if (step === 'credentials') return credentialsProblem(error);
  return codeProblem(error);
}

function tooMany(error: ApiError): LoginProblem {
  const seconds = error.retryAfter ?? 60;
  const what = error.code === 'login_code_unavailable' ? '지금은 코드를 보낼 수 없습니다.' : '시도가 너무 많습니다.';
  return { message: `${what} ${seconds}초 뒤에 다시 시도하세요.`, waitSeconds: seconds };
}

function credentialsProblem(error: ApiError): LoginProblem {
  if (error.status === 401) return { message: WRONG_CREDENTIALS };
  if (error.status === 403 && error.code === 'email_not_verified') return { message: NOT_VERIFIED };
  if (error.status === 400) return { message: '입력을 확인해 주세요.', fields: firstOfEach(error.fields) };
  return withRequestId(UNKNOWN, error);
}

function codeProblem(error: ApiError): LoginProblem {
  if (error.status === 401) return { message: TICKET_GONE, restart: true };
  if (error.status === 400) return { message: error.message, fields: firstOfEach(error.fields) };
  return withRequestId(UNKNOWN, error);
}

function withRequestId(message: string, error: ApiError): LoginProblem {
  return error.requestId ? { message, requestId: error.requestId } : { message };
}

function firstOfEach(fields: Record<string, string[]>): Record<string, string> {
  const first: Record<string, string> = {};
  for (const [name, messages] of Object.entries(fields)) {
    if (messages[0]) first[name] = messages[0];
  }
  return first;
}
