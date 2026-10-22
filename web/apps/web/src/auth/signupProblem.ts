// web/apps/web/src/auth/signupProblem.ts
// 가입의 실패를 화면에 보일 것으로 바꾼다(화면 명세 A2 의 "버튼이 비활성인 조건"의 가입 줄). 순수한 함수다.

import { ApiError } from '../api/errors';
import { commonProblem, fieldProblem, unknownProblem, type FormProblem } from './problem';

export type SignupStep = 'email' | 'code' | 'profile';

export type SignupProblem = FormProblem & {
  /** 이미 가입을 마친 이메일이다. 로그인으로 보낸다 */
  goToLogin?: boolean;
  /** 동의 항목의 판이 바뀌었다. 항목을 다시 읽고 다시 체크받는다 */
  consentsChanged?: boolean;
};

const SIGNUP_FAILED = '가입하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
const TICKET_GONE = '가입 시간이 지났습니다. 이메일부터 다시 인증해 주세요.';
const ALREADY_REGISTERED = '이미 가입을 마친 이메일입니다. 로그인해 주세요.';
const CONSENTS_CHANGED = '동의 항목이 바뀌었습니다. 새 문서를 보고 다시 체크해 주세요.';
const NAME_TAKEN = '방금 다른 가입이 같은 아이디나 닉네임을 가져갔습니다. 다른 것을 골라 주세요.';

export function describeSignupProblem(error: unknown, step: SignupStep): SignupProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: SIGNUP_FAILED };
  if (step === 'email') return emailProblem(error);
  if (step === 'code') return codeProblem(error);
  return profileProblem(error);
}

function emailProblem(error: ApiError): SignupProblem {
  if (error.status === 400) return fieldProblem(error, '이메일을 확인해 주세요.');
  return unknownProblem(error, SIGNUP_FAILED);
}

function codeProblem(error: ApiError): SignupProblem {
  if (error.status === 400) return fieldProblem(error, error.message);
  return unknownProblem(error, SIGNUP_FAILED);
}

function profileProblem(error: ApiError): SignupProblem {
  if (error.status === 400 && error.code === 'signup_ticket_invalid') return { message: TICKET_GONE, restart: true };
  if (error.status === 400 && error.fields.consents) return { message: CONSENTS_CHANGED, consentsChanged: true };
  if (error.status === 400) return fieldProblem(error, '입력을 확인해 주세요.');
  if (error.status === 409 && error.code === 'email_registered') return { message: ALREADY_REGISTERED, goToLogin: true };
  if (error.status === 409) return fieldProblem(error, NAME_TAKEN);
  return unknownProblem(error, SIGNUP_FAILED);
}
