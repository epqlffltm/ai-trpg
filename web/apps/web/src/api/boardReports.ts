// web/apps/web/src/api/boardReports.ts
// 게시판의 신고 처리(E4, 게시판 서버). 운영자만 부른다(토큰의 roles 의 operator). 운영자가 아니면 403 이다.
//   - 열린 신고를 신고당한 것(글이나 댓글)마다 한 줄로 묶은 목록. 처음 신고가 이른 것부터. 쪽 번호(page, size 1~50, total)
//   - 한 글이나 댓글에 걸린 신고 모두(처리한 것도, 설명과 신고한 사람까지). 최근 것부터
//   - 처리는 그것에 걸린 열린 신고를 한 번에 닫는다. actioned(조치함) 또는 dismissed(문제없음). 열린 신고가 없으면 404
// 글이나 댓글을 지우는 것은 처리와 따로다(게시판의 지우기). 지운 것에 걸린 신고도 닫아야 목록에서 빠진다.
// 타입은 생성 타입에서 바로 가져온다.

import type { components } from './generated/board';
import { apiRequest } from './http';

type Schemas = components['schemas'];
export type BoardReportGroupPage = Schemas['OpenReportGroupPageResponse'];
export type BoardReportGroup = Schemas['OpenReportGroupResponse'];
export type BoardReportTarget = Schemas['ReportTargetResponse'];
export type BoardReportPage = Schemas['ReportPageResponse'];
export type BoardReport = Schemas['ReportResponse'];
export type BoardReportOutcome = Schemas['HandleReportsDto']['outcome'];

const BOARD = '/api/v1/board';

/** 한 쪽의 수(서버는 1~50) */
export const BOARD_REPORT_PAGE_SIZE = 20;

/** 신고당한 것. 글이면 posts, 댓글이면 comments 아래다 */
export type ReportedItem = Pick<BoardReportTarget, 'type' | 'id'>;

function itemPath(item: ReportedItem): string {
  return `${BOARD}/${item.type === 'post' ? 'posts' : 'comments'}/${encodeURIComponent(item.id)}/reports`;
}

export function fetchBoardReportGroups(page: number, signal?: AbortSignal): Promise<BoardReportGroupPage> {
  return apiRequest<BoardReportGroupPage>(`${BOARD}/reports`, { query: { page, size: BOARD_REPORT_PAGE_SIZE }, ...(signal ? { signal } : {}) });
}

export function fetchBoardItemReports(item: ReportedItem, page: number, signal?: AbortSignal): Promise<BoardReportPage> {
  return apiRequest<BoardReportPage>(itemPath(item), { query: { page, size: BOARD_REPORT_PAGE_SIZE }, ...(signal ? { signal } : {}) });
}

export function closeBoardReports(item: ReportedItem, outcome: BoardReportOutcome): Promise<void> {
  return apiRequest<void>(`${itemPath(item)}/outcome`, { method: 'PUT', body: { outcome } });
}
