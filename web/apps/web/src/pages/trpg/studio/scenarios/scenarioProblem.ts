// web/apps/web/src/pages/trpg/studio/scenarios/scenarioProblem.ts
// 시나리오의 저장과 게시의 실패를 보일 것으로 바꾼다. 순수한 함수다. 재료와 같은 실패(404, 409, 422)는 재료의 글을 쓴다.
//
// 시나리오에만 있는 답(trpg-server/app/assets/scenarios/router.py, app/assets/routing.py):
//   - 403 code adult_content_required: 성인 확인을 하지 않고 성인용으로 저장했다
//   - 422 {field: narration_model, reason}: 추천 서술 모델이 없거나(missing) 서비스 중이 아니다(not_offered)
//   - 409 {problems}(게시): 게시할 조건을 갖추지 못했다. 무엇인지는 점검 패널이 보인다

import { ApiError } from '../../../../api/errors';
import { commonProblem, type FormProblem } from '../../../../auth/problem';
import { describeSaveProblem } from '../studioProblem';

const ADULT_ONLY = '성인용은 본인인증으로 성인 확인을 한 사람만 고를 수 있습니다.';
const MODEL_NOT_OFFERED = '지금 서비스하지 않는 모델입니다. 추천 서술 모델을 다시 골라 주세요.';
const NOT_READY = '게시할 조건을 갖추지 못했습니다. 게시 점검의 문제를 고친 뒤 다시 게시하세요.';

function isAdultOnly(error: ApiError): boolean {
  return error.status === 403 && error.code === 'adult_content_required';
}

function isModelProblem(error: ApiError): boolean {
  return error.status === 422 && error.body.field === 'narration_model';
}

/** 만들기와 고치기 */
export function describeScenarioSaveProblem(error: unknown): FormProblem {
  if (commonProblem(error) || !(error instanceof ApiError)) return describeSaveProblem(error, 'scenarios');
  if (isAdultOnly(error)) return { message: ADULT_ONLY, fields: { rating: ADULT_ONLY } };
  if (isModelProblem(error)) return { message: MODEL_NOT_OFFERED, fields: { narration_model: MODEL_NOT_OFFERED } };
  return describeSaveProblem(error, 'scenarios');
}

/** 게시 */
export function describePublishProblem(error: unknown): FormProblem {
  if (error instanceof ApiError && error.status === 409 && Array.isArray(error.body.problems)) return { message: NOT_READY };
  if (error instanceof ApiError && isAdultOnly(error)) return { message: ADULT_ONLY };
  return describeSaveProblem(error, 'scenarios');
}
