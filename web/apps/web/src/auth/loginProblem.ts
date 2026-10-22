// web/apps/web/src/auth/loginProblem.ts
// 로그인의 실패를 화면에 보일 것으로 바꾼다(화면 명세 A2 의 "버튼이 비활성인 조건"). 화면을 그리지 않는 순수한 함수다.
//
// 아이디가 없는 것과 비밀번호가 틀린 것, 정지된 계정을 가르지 않는다. 서버도 같은 401 을 준다.

import { ApiError } from '../api/errors';
import { commonProblem, fieldProblem, unknownProblem, type FormProblem } from './problem';

export type LoginStep = 'credentials' | 'code';
export type LoginProblem = FormProblem;

const WRONG_CREDENTIALS = '아이디 또는 비밀번호가 맞지 않습니다. 계속 안 되면 문의해 주세요.';
const NOT_VERIFIED = '가입할 때 받은 메일의 인증을 아직 마치지 않았습니다. 가입을 처음부터 다시 진행해 주세요.';
const TICKET_GONE = '로그인 시간이 지났습니다. 아이디와 비밀번호부터 다시 입력해 주세요.';
const LOGIN_FAILED = '로그인하지 못했습니다. 잠시 뒤에 다시 시도하세요.';

export function describeLoginProblem(error: unknown, step: LoginStep): LoginProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: LOGIN_FAILED };
  return step === 'credentials' ? credentialsProblem(error) : codeProblem(error);
}

function credentialsProblem(error: ApiError): LoginProblem {
  if (error.status === 401) return { message: WRONG_CREDENTIALS };
  if (error.status === 403 && error.code === 'email_not_verified') return { message: NOT_VERIFIED };
  if (error.status === 400) return fieldProblem(error, '입력을 확인해 주세요.');
  return unknownProblem(error, LOGIN_FAILED);
}

function codeProblem(error: ApiError): LoginProblem {
  if (error.status === 401) return { message: TICKET_GONE, restart: true };
  if (error.status === 400) return fieldProblem(error, error.message);
  return unknownProblem(error, LOGIN_FAILED);
}
