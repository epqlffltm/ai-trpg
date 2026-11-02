// web/apps/web/src/pages/trpg/room/status/raiseProblem.ts
// 쌓인 점수를 능력치에 놓지 못한 까닭을 화면에 보일 것으로(#286). 순수한 함수다(trpg-server/app/tables/raising.py).
//   - 409: 라운드가 닫는 중(round_closing), 진행 중이 아님, 죽음, 점수가 모자람(not_enough_points), 상한(ability_at_max).
//     어느 것이든 그 사이에 테이블이 바뀐 것이라 테이블을 다시 읽는다
//   - 422: 규칙에 없는 능력치이거나 놓을 점수가 맞지 않다
//   - 404: 이 테이블에 앉아 있지 않다

import { ApiError } from '../../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../../auth/problem';

export type RaiseProblem = FormProblem & { refresh?: boolean };

const FAILED = '능력치를 올리지 못했습니다. 잠시 뒤에 다시 시도하세요.';

const CONFLICTS: Record<string, string> = {
  round_closing: '라운드를 마감하는 중에는 능력치를 올릴 수 없습니다. 다음 라운드에 올려 주세요.',
  not_playing: '진행 중인 테이블이 아닙니다.',
  not_started: '아직 시작하지 않은 테이블입니다.',
  character_dead: '죽은 캐릭터는 능력치를 올릴 수 없습니다.',
  not_enough_points: '남은 점수가 모자랍니다.',
  ability_at_max: '규칙의 상한을 넘는 능력치가 있습니다.',
};

export function describeRaiseProblem(error: unknown): RaiseProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 409) return { message: CONFLICTS[error.code ?? ''] ?? FAILED, refresh: true };
  if (error.status === 422) return { message: '올릴 수 없는 능력치가 있습니다.', refresh: true };
  if (error.status === 404) return { message: '이 테이블에 앉아 있지 않습니다.', refresh: true };
  return unknownProblem(error, FAILED);
}
