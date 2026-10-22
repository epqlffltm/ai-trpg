// web/apps/web/src/pages/trpg/room/character/characterProblem.ts
// 캐릭터 정하기와 굴리기(B5)의 실패를 화면에 보일 것으로 바꾼다. 순수한 함수다.
//
// 게임 서버의 답(trpg-server/app/tables/characters.py, rolls.py):
//   - 409: 테이블의 지금 상태와 부딪힌다. 까닭은 reason(ApiError.code)
//   - 422: 없는 프리젠이거나 능력치가 규칙에 맞지 않는다. 본문은 "<칸> 에 고를 수 없는 값이 있습니다." 다
// refresh 가 켜지면 테이블을 다시 읽는다(그 사이 남이 프리젠을 가져갔거나, 테이블이 시작했다).

import { ApiError } from '../../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../../auth/problem';
import { optionField } from '../../tables/tableProblem';

export type CharacterProblem = FormProblem & { refresh?: boolean };

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';

const CONFLICTS: Record<string, CharacterProblem> = {
  pregen_taken: { message: '그 사이에 다른 사람이 가져간 프리젠입니다. 다른 것을 골라 주세요.', refresh: true },
  character_mode_not_allowed: { message: '이 테이블에서 쓸 수 없는 방식입니다.', refresh: true },
  not_rolled: { message: '먼저 주사위를 굴려 주세요.', refresh: true },
  already_rolled: { message: '이 캐릭터를 위해 이미 굴렸습니다. 방장이 "한 번 더"를 주면 다시 굴릴 수 있습니다.', refresh: true },
  not_recruiting: { message: '이미 시작했거나 끝난 테이블입니다.', refresh: true },
};

const OPTION_FIELDS: Record<string, string> = {
  pregen_index: '없는 프리젠입니다. 새로 고쳐 주세요.',
  abilities: '능력치가 이 테이블의 규칙에 맞지 않습니다. 범위와 총점, 굴린 점수를 확인해 주세요.',
};

/** 캐릭터 정하기(PUT .../character)와 굴리기(POST .../character/roll) */
export function describeCharacterProblem(error: unknown): CharacterProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 404) return { message: '이 테이블에 앉아 있지 않습니다.', refresh: true };
  if (error.status === 409) return CONFLICTS[error.code ?? ''] ?? unknownProblem(error, FAILED);
  if (error.status === 422) return optionProblem(error);
  return unknownProblem(error, FAILED);
}

function optionProblem(error: ApiError): CharacterProblem {
  const field = optionField(error.message);
  const message = field ? OPTION_FIELDS[field] : undefined;
  return message ? { message } : unknownProblem(error, '보낸 값이 맞지 않습니다. 새로 고쳐 다시 시도해 주세요.');
}
