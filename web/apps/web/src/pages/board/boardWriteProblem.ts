// web/apps/web/src/pages/board/boardWriteProblem.ts
// 글, 댓글, 신고, 고정을 하지 못한 까닭을 폼의 모양(FormProblem)으로. 순수한 함수다. 까닭은 api/board.ts 의 머리말을 본다.
// 게시판 서버의 403·404·409 와 칸을 가르지 않는 400 의 detail 은 사람에게 보일 문장이라 그대로 쓴다.

import { ApiError } from '../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../auth/problem';

export type BoardWriteAction = '글' | '댓글' | '신고' | '고정';

const TOO_OFTEN: Record<BoardWriteAction, string> = {
  글: '글을 너무 자주 썼습니다.',
  댓글: '댓글을 너무 자주 달았습니다.',
  신고: '신고를 너무 자주 했습니다.',
  고정: '너무 자주 시도했습니다.',
};

const SIGNED_OUT = '로그인이 끝났습니다. 다시 로그인한 뒤에 해 주세요.';

export function describeBoardWriteProblem(error: unknown, action: BoardWriteAction): FormProblem {
  if (error instanceof ApiError && error.status === 429) return tooOften(error, action);
  const common = commonProblem(error);
  if (common) return common;
  const api = error as ApiError;
  if (api.status === 401) return { message: SIGNED_OUT };
  if (api.status === 400 && Object.keys(api.fields).length > 0) return { message: '적은 것을 확인해 주세요.', fields: firstMessages(api) };
  if ([400, 403, 404, 409].includes(api.status)) return { message: api.message };
  return unknownProblem(api);
}

function tooOften(error: ApiError, action: BoardWriteAction): FormProblem {
  const seconds = error.retryAfter ?? 60;
  return { message: `${TOO_OFTEN[action]} ${seconds}초 뒤에 다시 해 주세요.`, waitSeconds: seconds };
}

function firstMessages(error: ApiError): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const [name, messages] of Object.entries(error.fields)) {
    if (messages[0]) fields[name] = messages[0];
  }
  return fields;
}
