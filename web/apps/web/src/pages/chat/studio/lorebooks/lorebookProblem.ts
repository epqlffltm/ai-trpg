// web/apps/web/src/pages/chat/studio/lorebooks/lorebookProblem.ts
// 로어북의 만들기, 저장, 지우기, 게시의 실패를 보일 것으로 바꾼다. 순수한 함수다.
//
// asset 서버의 답(asset-server/app/lorebooks/router.py):
//   - 403 code operator_only: 지금(1~2단계)은 운영자만 만든다
//   - 404 code lorebook_not_found: 그런 로어북이 없다. 남의 것도 404 다
//   - 422: 받지 않는 값. 화면이 먼저 검사하므로 서버의 규칙이 바뀌었을 때만 온다

import { ApiError } from '../../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../../auth/problem';

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
const OPERATOR_ONLY = '지금은 운영자만 로어북을 만들 수 있습니다.';
const MISSING = '로어북을 찾을 수 없습니다. 지워졌을 수 있습니다.';

export function describeLorebookProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 403 && error.code === 'operator_only') return { message: OPERATOR_ONLY };
  if (error.status === 404) return { message: MISSING };
  if (error.status === 422) return { message: '서버가 받지 않는 값이 있습니다. 칸을 다시 확인해 주세요.' };
  return unknownProblem(error, FAILED);
}

/** 하나를 읽지 못한 까닭이 "없다"인가(404, 주소의 id 가 틀린 422) */
export function isMissingLorebook(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 422);
}
