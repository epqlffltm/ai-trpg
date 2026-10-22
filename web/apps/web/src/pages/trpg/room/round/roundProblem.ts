// web/apps/web/src/pages/trpg/room/round/roundProblem.ts
// 선언 내기와 라운드 닫기의 실패를 화면에 보일 것으로 바꾼다. 순수한 함수다.
//
// 게임 서버의 답(trpg-server/app/rounds/router.py, errors.py):
//   - 409: 테이블이나 라운드의 지금 상태와 부딪힌다. 까닭은 reason(ApiError.code)
//   - 422: 행동이 규칙에 없는 것을 가리키거나(action.<칸> 가 이 테이블의 규칙에 없습니다), 겨눌 수 없는 대상이다
//   - 403: 방장이 아니다(닫기)
// refresh 가 켜지면 라운드를 다시 읽는다(그 사이 마감했거나 다음 라운드가 열렸다).

import { ApiError } from '../../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../../auth/problem';

export type RoundProblem = FormProblem & { refresh?: boolean };

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';

const CONFLICTS: Record<string, RoundProblem> = {
  round_closing: { message: '그 사이에 선언을 마감했습니다. 결과를 기다려 주세요.', refresh: true },
  not_playing: { message: '진행 중인 테이블이 아닙니다.', refresh: true },
  not_started: { message: '아직 시작하지 않은 테이블입니다.', refresh: true },
  character_downed: { message: '캐릭터가 쓰러져 있어 판정을 붙일 수 없습니다. 글만 낼 수 있습니다.' },
  character_incapacitated: { message: '캐릭터가 입은 부상 때문에 판정을 붙일 수 없습니다. 글만 낼 수 있습니다.' },
  character_dead: { message: '캐릭터가 죽어 선언을 낼 수 없습니다.', refresh: true },
  character_arriving: { message: '이번 라운드에 들어온 캐릭터입니다. 다음 라운드부터 선언합니다.', refresh: true },
};

/** 선언 내기(PUT .../rounds/current/declaration) */
export function describeDeclarationProblem(error: unknown): RoundProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 404) return { message: '이 테이블에 앉아 있지 않습니다.', refresh: true };
  if (error.status === 409) return CONFLICTS[error.code ?? ''] ?? unknownProblem(error, FAILED);
  if (error.status === 422) return { message: '판정의 능력이나 난이도가 이 테이블의 규칙에 없습니다. 새로 고쳐 주세요.' };
  return unknownProblem(error, FAILED);
}

/** 라운드 닫기와 서술 다시 맡기기(방장, POST .../rounds/current/close) */
export function describeCloseProblem(error: unknown): RoundProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 403) return { message: '방장만 라운드를 닫을 수 있습니다.', refresh: true };
  if (error.status === 409) return { ...(CONFLICTS[error.code ?? ''] ?? { message: FAILED }), refresh: true };
  return unknownProblem(error, FAILED);
}
