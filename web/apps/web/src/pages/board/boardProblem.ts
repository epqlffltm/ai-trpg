// web/apps/web/src/pages/board/boardProblem.ts
// 게시판을 읽지 못한 까닭을 화면의 한 줄로. 순수한 함수다. 까닭은 api/board.ts 의 머리말을 본다.

import { ApiError, isInputError, NetworkError } from '../../api/errors';

export function boardProblemText(error: unknown, what: '목록' | '글' | '댓글' | '검색'): string {
  if (error instanceof NetworkError) return '서버에 닿지 못했습니다. 연결을 확인하고 다시 시도하세요.';
  if (!(error instanceof ApiError)) return `${what}을 불러오지 못했습니다. 잠시 뒤에 다시 시도하세요.`;
  if (error.status === 404) return what === '글' ? '없는 글이거나 지운 글입니다.' : '없는 게시판입니다.';
  if (isInputError(error)) return Object.values(error.fields)[0]?.[0] ?? '검색어를 확인해 주세요.';
  if (error.status === 503 && what === '검색') return '검색이 오래 걸려 멈췄습니다. 낱말을 줄이거나 게시판을 골라 다시 찾아 주세요.';
  if (error.status === 503) return `게시판 서버가 지금 답하지 못합니다.${error.retryAfter ? ` ${error.retryAfter}초 뒤에` : ' 잠시 뒤에'} 다시 시도하세요.`;
  return `${what}을 불러오지 못했습니다. 잠시 뒤에 다시 시도하세요.`;
}
