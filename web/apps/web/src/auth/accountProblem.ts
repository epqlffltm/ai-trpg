// web/apps/web/src/auth/accountProblem.ts
// 계정 화면(마이페이지의 비밀번호와 닉네임 바꾸기, 다시 동의, 탈퇴 요청과 취소)의 실패를 화면에 보일 것으로 바꾼다. 순수한 함수다.

import { ApiError } from '../api/errors';
import { commonProblem, fieldProblem, unknownProblem, type FormProblem } from './problem';

export type ConsentProblem = FormProblem & {
  /** 문서의 판이 바뀌었다. 상태를 다시 읽고 새 판으로 다시 받는다 */
  consentsChanged?: boolean;
};

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
const CONSENTS_CHANGED = '문서의 판이 바뀌었습니다. 새 판을 읽고 다시 동의해 주세요.';
const REQUIRED_ITEM = '필수 항목은 끌 수 없습니다. 철회하려면 탈퇴해야 합니다.';
const NICKNAME_TOO_SOON = '닉네임은 30일에 한 번 바꿀 수 있습니다.';

/** 비밀번호 바꾸기. 현재 비밀번호가 틀렸거나 새 비밀번호가 규칙에 어긋나면 그 칸에 서버의 글을 보인다 */
export function describePasswordChangeProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 400) return fieldProblem(error, '입력을 확인해 주세요.');
  return unknownProblem(error, FAILED);
}

/** 닉네임 바꾸기. 비밀번호나 이름이 틀리면 그 칸에 서버의 글을 보인다. 30일 안이면 언제부터인지는 화면이 /me 로 보인다 */
export function describeNicknameChangeProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 400) return fieldProblem(error, '입력을 확인해 주세요.');
  if (error.status === 409 && error.code === 'nickname_change_too_soon') return { message: NICKNAME_TOO_SOON };
  return unknownProblem(error, FAILED);
}

/** 탈퇴 요청. 비밀번호가 틀리면 그 칸에 서버의 글을 보인다. 너무 많이 틀리면 기다리게 한다(429) */
export function describeWithdrawalProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 400) return fieldProblem(error, '비밀번호를 확인해 주세요.');
  return unknownProblem(error, FAILED);
}

/** 동의하기와 철회하기. 판이 바뀌었으면 다시 읽게 한다 */
export function describeConsentProblem(error: unknown): ConsentProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 409 && error.code === 'consent_outdated') {
    return { message: CONSENTS_CHANGED, consentsChanged: true };
  }
  if (error.status === 400 && error.code === 'consent_required') return { message: REQUIRED_ITEM };
  return unknownProblem(error, FAILED);
}

/** 칸이 없는 계정의 동작(모든 기기 로그아웃, 탈퇴 취소, 새 토큰 받기) */
export function describeAccountProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  return unknownProblem(error, FAILED);
}
