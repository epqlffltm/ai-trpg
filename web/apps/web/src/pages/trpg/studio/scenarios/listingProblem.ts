// web/apps/web/src/pages/trpg/studio/scenarios/listingProblem.ts
// 소개 페이지 고치기와 공개의 실패를 보일 것으로 바꾼다. 순수한 함수다. 나머지 실패(404, 422 …)는 재료의 글을 쓴다.
//
// 소개와 공개에만 있는 답(trpg-server/app/listings/router.py, app/operators/router.py):
//   - 409 {problems}: 한줄소개나 장르가 없다(공개할 때, 공개 중에 비울 때)
//   - 403 code version_sanctioned: 운영자가 제재한 판이다. 고쳐서 새 판을 내면 공개할 수 있다
//   - 403 code publishing_banned: 공개 금지 중이다. 운영자가 풀 때까지 공개하지 못한다
//   - 403 code adult_content_required: 성인 확인을 하지 않았는데 성인용이다

import { ApiError } from '../../../../api/errors';
import { commonProblem, type FormProblem } from '../../../../auth/problem';
import { describeSaveProblem } from '../studioProblem';
import { knownListingProblems, listingProblemText } from './listingForm';

const REFUSALS: Record<string, string> = {
  version_sanctioned: '운영자가 제재한 판이라 공개할 수 없습니다. 고쳐서 새 판을 게시한 뒤 그 판을 공개하세요.',
  publishing_banned: '공개 금지 중이라 공개할 수 없습니다. 운영자가 풀 때까지 기다려 주세요.',
  adult_content_required: '성인용은 본인인증으로 성인 확인을 한 사람만 고치거나 공개할 수 있습니다.',
};

/** 409 의 까닭을 한 줄로. 모르는 까닭뿐이면 null */
function notReadyText(error: ApiError, lead: string): string | null {
  if (error.status !== 409) return null;
  const problems = knownListingProblems(error.body.problems);
  if (problems.length === 0) return null;
  return `${lead} ${problems.map(listingProblemText).join(' ')}`;
}

/** 403 의 code 를 글로. 모르는 code 면 null */
function refusalText(error: ApiError): string | null {
  if (error.status !== 403 || !error.code) return null;
  return REFUSALS[error.code] ?? null;
}

/** 소개 페이지 고치기 */
export function describeListingProblem(error: unknown): FormProblem {
  if (commonProblem(error) || !(error instanceof ApiError)) return describeSaveProblem(error, 'scenarios');
  const text = notReadyText(error, '공개 중이라 비울 수 없습니다. 먼저 게시 탭에서 공개를 내리세요.') ?? refusalText(error);
  return text ? { message: text } : describeSaveProblem(error, 'scenarios');
}

/** 공개와 공개 내리기 */
export function describePublicationProblem(error: unknown): FormProblem {
  if (commonProblem(error) || !(error instanceof ApiError)) return describeSaveProblem(error, 'scenarios');
  if (error.status === 404) return { message: '그 판이나 시나리오가 없습니다. 판의 목록을 다시 불러 주세요.' };
  const text = notReadyText(error, '소개 탭에서 한줄소개와 장르를 적어야 공개할 수 있습니다.') ?? refusalText(error);
  return text ? { message: text } : describeSaveProblem(error, 'scenarios');
}
