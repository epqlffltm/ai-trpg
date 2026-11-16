// web/apps/web/src/auth/stepUpProblem.ts
// 본인 확인(F5)의 실패를 화면에 보일 모양으로. 순수한 함수다(auth-server/README.md 의 "민감한 작업의 본인 확인").
//   - 400 step_up_code_invalid: 코드가 틀렸거나 만료됐다. 까닭을 나누지 않는다. 코드 칸에 보인다
//   - 409 step_up_session_unknown: 갱신해도 세션의 이름이 생기지 않았다. 다시 로그인하면 생긴다
//   - 403 step_up_required: (끄기) 확인을 마치지 않았다
//   - 429 step_up_code_unavailable: 코드를 너무 자주 받으려 했다. 기다릴 초가 붙는다(commonProblem)

import { ApiError } from '../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from './problem';

export const CODE_INVALID = '인증 코드가 올바르지 않거나 만료되었습니다.';

export function describeStepUpProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common) return common;
  const apiError = error as ApiError;
  if (apiError.code === 'step_up_code_invalid') return { message: CODE_INVALID, fields: { code: CODE_INVALID } };
  if (apiError.code === 'step_up_session_unknown') {
    return { message: '이 기기의 로그인 정보가 오래되었습니다. 로그아웃한 뒤 다시 로그인해 주세요.' };
  }
  if (apiError.code === 'step_up_required') return { message: '본인 확인을 끄려면 먼저 본인 확인을 마쳐 주세요.' };
  return unknownProblem(apiError);
}
