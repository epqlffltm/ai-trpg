// web/apps/web/src/pages/trpg/room/roomProblem.ts
// 테이블 방의 실패(시작, 채팅, 나가기)를 화면에 보일 것으로 바꾼다. 순수한 함수다.
// 409 의 까닭은 reason 이다(ApiError.code 로 읽는다. trpg-server/app/tables/errors.py 의 Conflict).

import { ApiError } from '../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../auth/problem';

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';

const START_CONFLICTS: Record<string, string> = {
  characters_missing: '캐릭터를 정하지 않은 사람이 있습니다. 모두 정한 뒤에 시작할 수 있습니다.',
  pregens_too_few: '프리젠만 허용한 테이블인데 앉은 사람이 프리젠보다 많습니다.',
  story_too_long: '시나리오의 글이 서술에 넣을 수 있는 길이를 넘어 시작할 수 없습니다. 제작자에게 알려 주세요.',
  not_recruiting: '이미 시작했거나 끝난 테이블입니다.',
};

/** 테이블 시작(방장) */
export function describeStartProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 403) return { message: '방장만 시작할 수 있습니다.' };
  if (error.status === 409) return { message: START_CONFLICTS[error.code ?? ''] ?? FAILED };
  return unknownProblem(error, FAILED);
}

/** 채팅 쓰기. 끝난 테이블이면 409, 너무 빨리 쓰면 429(10초에 5줄) */
export function describeChatProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 409) return { message: '끝난 테이블에는 채팅을 쓸 수 없습니다.' };
  if (error.status === 404) return { message: '이 테이블에 앉아 있지 않습니다.' };
  return unknownProblem(error, FAILED);
}

/** 그 밖의 동작(나가기) */
export function describeRoomProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  return unknownProblem(error, FAILED);
}
