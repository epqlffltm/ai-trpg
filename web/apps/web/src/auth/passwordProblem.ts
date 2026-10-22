// web/apps/web/src/auth/passwordProblem.ts
// 비밀번호 재설정의 실패를 화면에 보일 것으로 바꾼다. 순수한 함수다.
// 링크(이메일과 토큰)가 틀렸거나 만료됐으면 다시 요청하게 한다. 새 비밀번호가 규칙에 어긋나면 그 칸에 서버의 글을 보인다.

import { ApiError } from '../api/errors';
import { commonProblem, fieldProblem, unknownProblem, type FormProblem } from './problem';

export type PasswordStep = 'request' | 'confirm';

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
const LINK_GONE = '링크가 틀렸거나 만료됐습니다. 재설정 메일을 다시 받아 주세요.';

export function describePasswordProblem(error: unknown, step: PasswordStep): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status !== 400) return unknownProblem(error, FAILED);
  if (step === 'request') return fieldProblem(error, '이메일을 확인해 주세요.');
  if (error.fields.new_password) return fieldProblem(error, '새 비밀번호를 확인해 주세요.');
  return { message: LINK_GONE, restart: true };
}
