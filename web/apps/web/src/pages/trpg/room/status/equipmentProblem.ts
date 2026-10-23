// web/apps/web/src/pages/trpg/room/status/equipmentProblem.ts
// 착용과 벗기의 실패를 화면에 보일 것으로. 순수한 함수다(trpg-server/app/tables/wearing.py).
//   - 409: 라운드가 닫는 중(round_closing), 진행 중이 아님, 쓰러짐·죽음, 그 물건이 없음(not_enough_items). 테이블을 다시 읽는다
//   - 422: 그 칸에 끼울 수 없는 물건이거나 칸이 맞지 않다
//   - 404: 이 테이블에 앉아 있지 않다

import { ApiError } from '../../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../../auth/problem';

export type EquipmentProblem = FormProblem & { refresh?: boolean };

const FAILED = '장비를 바꾸지 못했습니다. 잠시 뒤에 다시 시도하세요.';

const CONFLICTS: Record<string, string> = {
  round_closing: '라운드를 마감하는 중에는 장비를 바꿀 수 없습니다. 다음 라운드에 바꿔 주세요.',
  not_playing: '진행 중인 테이블이 아닙니다.',
  not_started: '아직 시작하지 않은 테이블입니다.',
  character_downed: '쓰러진 캐릭터는 장비를 바꿀 수 없습니다.',
  character_dead: '죽은 캐릭터는 장비를 바꿀 수 없습니다.',
  not_enough_items: '그 물건을 가지고 있지 않습니다.',
};

export function describeEquipmentProblem(error: unknown): EquipmentProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 409) return { message: CONFLICTS[error.code ?? ''] ?? FAILED, refresh: true };
  if (error.status === 422) return { message: '그 물건은 고른 칸에 착용할 수 없습니다.', refresh: true };
  if (error.status === 404) return { message: '이 테이블에 앉아 있지 않습니다.', refresh: true };
  return unknownProblem(error, FAILED);
}
