// web/apps/web/src/pages/board/boardForm.ts
// 글, 댓글, 신고의 폼 값과 보내기 전의 검사. 순수한 함수다. 상한과 규칙은 게시판 서버와 같다(board-server/README.md).
//   - 제목은 앞뒤 빈칸을 떼어 보낸다(서버도 뗀다). 본문과 댓글은 받은 그대로다. 빈칸만 적은 것은 받지 않는다
//   - 길이는 서버처럼 UTF-16 의 글자 수(String.length)로 센다. 입력 칸의 maxLength 와 같다
//   - 고치기는 바뀐 칸만 보낸다. 아무것도 바뀌지 않았으면 보내지 않는다

import type { BoardReportCreate, BoardReportReason, PostCreate, PostUpdate } from '../../api/types';

export const POST_LIMITS = { title: 100, content: 20_000 } as const;
export const COMMENT_LIMIT = 2_000;
export const REPORT_DESCRIPTION_LIMIT = 500;
/** 고정의 기본 날 수와 범위(서버의 PinPostDto) */
export const PIN_DAYS = { default: 7, min: 1, max: 365 } as const;

export const REPORT_REASONS: { value: BoardReportReason; label: string }[] = [
  { value: 'spam', label: '스팸, 광고' },
  { value: 'abuse', label: '욕설, 괴롭힘' },
  { value: 'sexual', label: '음란물' },
  { value: 'illegal', label: '불법 정보' },
  { value: 'other', label: '기타(설명을 꼭 적어 주세요)' },
];

export type PostDraft = { title: string; content: string };
export type PostDraftProblems = Partial<Record<keyof PostDraft, string>>;
export type ReportDraft = { reason: BoardReportReason | ''; description: string };
export type ReportDraftProblems = Partial<Record<keyof ReportDraft, string>>;

export const EMPTY_POST: PostDraft = { title: '', content: '' };
export const EMPTY_REPORT: ReportDraft = { reason: '', description: '' };

function isBlank(value: string): boolean {
  return value.trim() === '';
}

export function postDraftOf(post: PostDraft): PostDraft {
  return { title: post.title, content: post.content };
}

/** 글의 문제. 칸마다 하나 */
export function postDraftProblems(draft: PostDraft): PostDraftProblems {
  const problems: PostDraftProblems = {};
  if (isBlank(draft.title)) problems.title = '제목을 적어 주세요.';
  else if (draft.title.trim().length > POST_LIMITS.title) problems.title = `제목은 ${POST_LIMITS.title}자까지입니다.`;
  if (isBlank(draft.content)) problems.content = '본문을 적어 주세요.';
  else if (draft.content.length > POST_LIMITS.content) problems.content = `본문은 ${POST_LIMITS.content.toLocaleString('ko-KR')}자까지입니다.`;
  return problems;
}

export function postBody(draft: PostDraft): PostCreate {
  return { title: draft.title.trim(), content: draft.content };
}

/** 바뀐 칸만. 바뀐 것이 없으면 null */
export function postPatch(initial: PostDraft, draft: PostDraft): PostUpdate | null {
  const patch: PostUpdate = {};
  if (draft.title.trim() !== initial.title) patch.title = draft.title.trim();
  if (draft.content !== initial.content) patch.content = draft.content;
  return Object.keys(patch).length > 0 ? patch : null;
}

/** 댓글의 문제. 없으면 null */
export function commentProblem(content: string): string | null {
  if (isBlank(content)) return '내용을 적어 주세요.';
  return content.length > COMMENT_LIMIT ? `댓글은 ${COMMENT_LIMIT.toLocaleString('ko-KR')}자까지입니다.` : null;
}

/** 신고의 문제. 사유는 꼭, 기타면 설명도 꼭 */
export function reportDraftProblems(draft: ReportDraft): ReportDraftProblems {
  const problems: ReportDraftProblems = {};
  if (draft.reason === '') problems.reason = '사유를 골라 주세요.';
  if (draft.reason === 'other' && isBlank(draft.description)) problems.description = '기타는 설명을 적어 주세요.';
  else if (draft.description.length > REPORT_DESCRIPTION_LIMIT) problems.description = `설명은 ${REPORT_DESCRIPTION_LIMIT}자까지입니다.`;
  return problems;
}

/** 신고의 본문. 설명을 비우면 보내지 않는다. 사유를 고르지 않았으면 null */
export function reportBody(draft: ReportDraft): BoardReportCreate | null {
  if (draft.reason === '') return null;
  const description = draft.description.trim();
  return description === '' ? { reason: draft.reason } : { reason: draft.reason, description: draft.description };
}

/** 고정할 날 수. 1~365 의 정수가 아니면 null */
export function parsePinDays(value: string): number | null {
  const days = Number(value);
  return Number.isInteger(days) && days >= PIN_DAYS.min && days <= PIN_DAYS.max ? days : null;
}
