// web/apps/web/src/pages/trpg/tables/tableProblem.ts
// 테이블에 들어가기(B3)와 만들기(B4)의 실패를 화면에 보일 것으로 바꾼다. 순수한 함수다.
//
// 게임 서버의 답(trpg-server/app/tables/router.py 의 처리기):
//   - 404: 그런 테이블이 없다(초대 코드가 틀린 것도). 만들기에서는 시나리오를 볼 수 없다
//   - 403: 비밀번호가 틀렸다(code 없음). 성인용이면 code 가 adult_content_required
//   - 409: 테이블의 지금 상태와 부딪힌다. 까닭은 reason(ApiError.code 로 읽는다): table_full, not_recruiting, already_ended, already_seated
//   - 422: 고를 수 없는 것을 골랐다. 본문은 "<칸> 에 고를 수 없는 값이 있습니다." 이고 칸의 이름을 따로 싣지 않는다
//   - 429: 비밀번호를 너무 많이 틀렸다(retry_after)

import { ApiError } from '../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../auth/problem';

export type TableProblem = FormProblem & {
  /** 목록이 그 사이에 달라졌다. 다시 읽는다 */
  refresh?: boolean;
  /** 이미 앉아 있다. 그 테이블로 간다 */
  seated?: boolean;
};

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
const ADULT_ONLY = '성인 확인을 한 사람만 이용할 수 있는 테이블입니다. 본인인증으로 성인 확인을 해 주세요.';

/** 로비에서 들어가기, 초대 코드로 들어가기 */
export function describeJoinProblem(error: unknown): TableProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 403 && error.code === 'adult_content_required') return { message: ADULT_ONLY };
  if (error.status === 403) return { message: '비밀번호가 맞지 않습니다.', fields: { password: '비밀번호가 맞지 않습니다.' } };
  if (error.status === 404) return { message: '테이블을 찾을 수 없습니다. 초대 코드를 확인해 주세요.', refresh: true };
  if (error.status === 409) return conflictProblem(error);
  return unknownProblem(error, FAILED);
}

/** 테이블 만들기 */
export function describeCreateProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 403 && error.code === 'adult_content_required') return { message: ADULT_ONLY };
  if (error.status === 404) return { message: '이 시나리오로는 테이블을 만들 수 없습니다. 공개가 끝났을 수 있습니다.' };
  if (error.status === 422) return optionProblem(error);
  if (error.status === 503) return unknownProblem(error, error.message);
  return unknownProblem(error, FAILED);
}

/** 422 의 본문에서 틀린 칸의 이름을 읽는다("narration_model 에 고를 수 없는 값이 있습니다.") */
export function optionField(message: string): string | null {
  return /^([a-z_]+) 에 고를 수 없는/.exec(message)?.[1] ?? null;
}

function optionProblem(error: ApiError): FormProblem {
  const field = optionField(error.message);
  if (field === 'narration_model') {
    const message = '시나리오의 추천 모델을 지금 쓸 수 없습니다. 서술 모델을 골라 주세요.';
    return { message, fields: { narration_model: message } };
  }
  if (field === 'narration_steps') {
    const message = '고른 기억이나 장면의 단계를 그 모델이 지금 팔지 않습니다. 다시 골라 주세요.';
    return { message, fields: { narration_model: message } };
  }
  return { message: '고를 수 없는 값이 있습니다. 시나리오가 바뀌었을 수 있으니 새로 고쳐 주세요.' };
}

function conflictProblem(error: ApiError): TableProblem {
  switch (error.code) {
    case 'already_seated':
      return { message: '이미 앉아 있는 테이블입니다.', seated: true };
    case 'table_full':
      return { message: '그 사이에 자리가 찼습니다.', refresh: true };
    case 'not_recruiting':
    case 'already_ended':
      return { message: '이미 시작했거나 끝난 테이블입니다.', refresh: true };
    default:
      return unknownProblem(error, FAILED);
  }
}
