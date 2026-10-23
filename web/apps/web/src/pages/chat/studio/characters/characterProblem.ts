// web/apps/web/src/pages/chat/studio/characters/characterProblem.ts
// 캐릭터의 만들기, 저장, 지우기, 게시의 실패를 보일 것으로 바꾼다. 순수한 함수다.
//
// asset 서버의 답(asset-server/app/characters/router.py, app/ratings.py):
//   - 403 code operator_only: 지금(1~2단계)은 운영자만 만들고 공개로 둔다
//   - 403 code adult_content_required: 성인 확인을 하지 않고 성인용으로 저장했다
//   - 404: 그런 캐릭터가 없다. 남의 것도 404 다
//   - 422 code lorebook_not_owned: 붙이려는 로어북이 내 것이 아니거나 그사이 지워졌다
//   - 409 {problems}(게시): 게시할 조건을 갖추지 못했다. 무엇인지는 점검 패널이 보인다
//   - 422: 받지 않는 값. 화면이 먼저 검사하므로 서버의 규칙이 바뀌었을 때만 온다

import { ApiError } from '../../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../../auth/problem';

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
const OPERATOR_ONLY = '지금은 운영자만 캐릭터를 만들고 공개로 둘 수 있습니다.';
const ADULT_ONLY = '성인용은 본인인증으로 성인 확인을 한 사람만 고를 수 있습니다.';
const MISSING = '캐릭터를 찾을 수 없습니다. 지워졌을 수 있습니다.';
const NOT_OWNED = '붙일 수 없는 로어북이 있습니다. 그사이 지워졌을 수 있습니다. 로어북 목록을 다시 확인해 주세요.';
const NOT_READY = '게시할 조건을 갖추지 못했습니다. 게시 점검의 문제를 고친 뒤 다시 게시하세요.';

function isCode(error: ApiError, status: number, code: string): boolean {
  return error.status === status && error.code === code;
}

/** 만들기, 고치기, 지우기 */
export function describeCharacterProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (isCode(error, 403, 'operator_only')) return { message: OPERATOR_ONLY, fields: { visibility: OPERATOR_ONLY } };
  if (isCode(error, 403, 'adult_content_required')) return { message: ADULT_ONLY, fields: { rating: ADULT_ONLY } };
  if (error.status === 404) return { message: MISSING };
  if (isCode(error, 422, 'lorebook_not_owned')) return { message: NOT_OWNED };
  if (error.status === 422) return { message: '서버가 받지 않는 값이 있습니다. 칸을 다시 확인해 주세요.' };
  return unknownProblem(error, FAILED);
}

/** 게시 */
export function describeCharacterPublishProblem(error: unknown): FormProblem {
  if (error instanceof ApiError && error.status === 409 && Array.isArray(error.body.problems)) return { message: NOT_READY };
  return describeCharacterProblem(error);
}

/** 하나를 읽지 못한 까닭이 "없다"인가(404, 주소의 id 가 틀린 422) */
export function isMissingCharacter(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 422);
}
