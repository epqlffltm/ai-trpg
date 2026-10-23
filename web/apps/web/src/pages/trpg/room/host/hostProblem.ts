// web/apps/web/src/pages/trpg/room/host/hostProblem.ts
// 방장의 운영의 실패를 화면에 보일 것으로 바꾼다. 순수한 함수다.
//
// 게임 서버의 답(trpg-server/app/tables/router.py, service.py, rolls.py, references.py):
//   - 403: 방장이 아니다(그 사이 방장이 바뀌었다)
//   - 404: 그 참가자가 앉아 있지 않다(그 사이 나갔다)
//   - 409: 테이블의 지금 상태와 부딪힌다. 까닭은 reason(ApiError.code)
//   - 422: 고를 수 없는 값. 참고 자료는 판의 세계관이 허용하지 않으면 422 다
// refresh 가 켜지면 테이블을 다시 읽는다.

import { ApiError } from '../../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../../auth/problem';
import { optionField } from '../../tables/tableProblem';

export type HostProblem = FormProblem & { refresh?: boolean };

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';

const CONFLICTS: Record<string, string> = {
  already_ended: '이미 끝난 테이블입니다.',
  cannot_kick_self: '자기 자신은 내보낼 수 없습니다. 나가기를 쓰세요.',
  not_recruiting: '모집 중에만 바꿀 수 있습니다.',
  reroll_not_allowed: '이 테이블은 다시 굴리기를 허락하지 않습니다.',
  reroll_already_granted: '이미 "한 번 더"를 줬습니다. 그 사람이 아직 굴리지 않았습니다.',
  not_rolled: '그 사람이 아직 굴리지 않았습니다.',
  character_mode_not_allowed: '이 테이블은 주사위 방식을 쓰지 않습니다.',
  character_alive: '진행 중에는 캐릭터가 죽어 새 캐릭터를 굴리는 사람에게만 줄 수 있습니다.',
};

export function describeHostProblem(error: unknown): HostProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 403) return { message: '방장만 할 수 있습니다. 그 사이 방장이 바뀌었을 수 있습니다.', refresh: true };
  if (error.status === 404) return { message: '그 사람은 이미 테이블에 없습니다.', refresh: true };
  if (error.status === 409) return { message: CONFLICTS[error.code ?? ''] ?? FAILED, refresh: true };
  if (error.status === 422) return optionProblem(error);
  return unknownProblem(error, FAILED);
}

function optionProblem(error: ApiError): HostProblem {
  if (optionField(error.message) === 'references_enabled') {
    return { message: '이 시나리오는 참고 자료를 허용하지 않습니다.' };
  }
  return unknownProblem(error, '고를 수 없는 값입니다.');
}
