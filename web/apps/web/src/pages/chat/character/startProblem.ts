// web/apps/web/src/pages/chat/character/startProblem.ts
// 대화를 시작하지 못한 까닭을 화면의 한 줄로. 순수한 함수다. 까닭은 api/chatCharacters.ts 의 머리말을 본다.

import { ApiError, NetworkError } from '../../../api/errors';

export type StartProblem = {
  text: string;
  /** 본인인증(A3)으로 가는 길을 붙인다 */
  needsAdult: boolean;
  /** 판이 바뀌었을 수 있어 캐릭터를 다시 읽는다 */
  reread: boolean;
};

export function describeStartProblem(error: unknown): StartProblem {
  const problem = (text: string, extra: Partial<StartProblem> = {}): StartProblem => ({ text, needsAdult: false, reread: false, ...extra });
  if (error instanceof NetworkError) return problem('서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요.');
  if (!(error instanceof ApiError)) return problem('대화를 시작하지 못했습니다. 잠시 뒤에 다시 시도하세요.');
  if (error.status === 403 && error.code === 'adult_content_required') {
    return problem('성인 등급의 캐릭터는 본인인증으로 성인 확인을 하면 대화할 수 있습니다.', { needsAdult: true });
  }
  if (error.status === 404) return problem('지금은 대화할 수 없는 캐릭터입니다. 공개가 내려갔을 수 있습니다.', { reread: true });
  if (error.status === 422 && error.code === 'start_not_found') {
    return problem('고른 시작 상황이 새 판에 없습니다. 시작 상황을 다시 골라 주세요.', { reread: true });
  }
  if (error.status === 503) {
    return problem(`캐릭터를 가져오지 못했습니다.${error.retryAfter ? ` ${error.retryAfter}초 뒤에` : ' 잠시 뒤에'} 다시 시도하세요.`);
  }
  return problem('대화를 시작하지 못했습니다. 잠시 뒤에 다시 시도하세요.');
}
