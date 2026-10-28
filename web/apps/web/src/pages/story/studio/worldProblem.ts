// web/apps/web/src/pages/story/studio/worldProblem.ts
// 세계관의 만들기, 저장, 지우기, 게시의 실패를 보일 것으로 바꾼다. 순수한 함수다.
//
// asset 서버의 답(asset-server/app/worlds/service.py, router.py):
//   - 403 code operator_only: 지금(1~2단계)은 운영자만 만들고 공개로 둔다
//   - 403 code adult_content_required: 성인 확인을 하지 않고 성인용으로 저장했다
//   - 404: 그런 세계관이 없다. 남의 것도 404 다
//   - 422 code character_not_owned, lorebook_not_owned, image_not_owned: 내 것이 아닌(또는 지워진) 캐릭터, 로어북, 그림
//   - 409 {problems}(게시): 게시할 조건을 갖추지 못했다. 무엇인지는 점검 패널이 보인다
//   - 422: 받지 않는 값. 화면이 먼저 검사하므로 서버의 규칙이 바뀌었을 때만 온다. 칸이 틀린 것(errors)이면 그 칸에 보인다

import { ApiError, isInputError } from '../../../api/errors';
import { commonProblem, fieldProblem, unknownProblem, type FormProblem } from '../../../auth/problem';

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
const OPERATOR_ONLY = '지금은 운영자만 세계관을 만들고 공개로 둘 수 있습니다.';
const ADULT_ONLY = '성인용은 본인인증으로 성인 확인을 한 사람만 고를 수 있습니다.';
const MISSING = '세계관을 찾을 수 없습니다. 지워졌을 수 있습니다.';
const NOT_OWNED: Record<string, string> = {
  character_not_owned: '내 캐릭터가 아닌(또는 지워진) 캐릭터를 가리키는 인물이 있습니다.',
  lorebook_not_owned: '붙일 수 없는 로어북이 있습니다. 그사이 지워졌을 수 있습니다. 로어북 목록을 다시 확인해 주세요.',
  image_not_owned: '내가 올리지 않은 그림이 있습니다. 그림을 다시 올려 주세요.',
};
const NOT_READY = '게시할 조건을 갖추지 못했습니다. 게시 점검의 문제를 고친 뒤 다시 게시하세요.';
const REJECTED = '서버가 받지 않는 값이 있습니다. 칸을 다시 확인해 주세요.';

function isCode(error: ApiError, status: number, code: string): boolean {
  return error.status === status && error.code === code;
}

/** 만들기, 고치기, 지우기 */
export function describeWorldProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (isCode(error, 403, 'operator_only')) return { message: OPERATOR_ONLY, fields: { visibility: OPERATOR_ONLY } };
  if (isCode(error, 403, 'adult_content_required')) return { message: ADULT_ONLY, fields: { rating: ADULT_ONLY } };
  if (error.status === 404) return { message: MISSING };
  const owned = error.status === 422 && error.code ? NOT_OWNED[error.code] : undefined;
  if (owned) return { message: owned };
  if (isInputError(error)) return fieldProblem(error, REJECTED);
  if (error.status === 422) return { message: REJECTED };
  return unknownProblem(error, FAILED);
}

/** 게시 */
export function describeWorldPublishProblem(error: unknown): FormProblem {
  if (error instanceof ApiError && error.status === 409 && Array.isArray(error.body.problems)) return { message: NOT_READY };
  return describeWorldProblem(error);
}

/** 하나를 읽지 못한 까닭이 "없다"인가(404, 주소의 id 가 틀린 422) */
export function isMissingWorld(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 422);
}
