// web/apps/web/src/api/inquiryAdmin.ts
// 운영자의 문의함(인증 서버의 support 앱, /api/v1/auth/admin/inquiries). 사용자의 보내기와 내 문의는 api/inquiries.ts 다.
// 운영자가 아니면 모든 주소가 404 다(운영자 주소를 드러내지 않는다).
//
//   - 목록: 상자(status)마다 최근 것부터 한 쪽씩, 상자마다의 수(counts)
//   - 하나 열기: 처음 열면 읽음(read_at, read_by)이 적힌다
//   - 답: 한 번만. 이미 답했으면 409 inquiry.already_answered, 없으면 404 inquiry.not_found
//   - 지우기: 하나, 고른 것(ids, 100개까지), 상자째(folder). 지운 일은 처리 기록(actions)에 남는다

import type { components as Auth } from './generated/auth';
import { apiRequest } from './http';

export type AdminInquiry = Auth['schemas']['OperatorInquiry'];
export type AdminInquiryPage = Auth['schemas']['OperatorInquiryPage'];
export type InquiryCounts = Auth['schemas']['FolderCounts'];
export type InquiryFolder = Auth['schemas']['FolderEnum'];
export type InquiryAction = Auth['schemas']['InquiryAction'];
export type InquiryActionPage = Auth['schemas']['InquiryActionPage'];

const ADMIN = '/api/v1/auth/admin/inquiries';

/** 상자의 목록과 상자마다의 수. status 가 없으면 모두 */
export function fetchAdminInquiries(status: 'open' | 'answered' | undefined, before: string | undefined, signal?: AbortSignal): Promise<AdminInquiryPage> {
  return apiRequest<AdminInquiryPage>(ADMIN, { query: { status, before }, ...(signal ? { signal } : {}) });
}

/** 문의 하나. 처음 열면 읽음으로 적힌다 */
export function fetchAdminInquiry(id: string, signal?: AbortSignal): Promise<AdminInquiry> {
  return apiRequest<AdminInquiry>(`${ADMIN}/${id}`, signal ? { signal } : {});
}

/** 답을 적고 문의의 주소로 메일을 보낸다 */
export function replyToInquiry(id: string, reply: string): Promise<AdminInquiry> {
  return apiRequest<AdminInquiry>(`${ADMIN}/${id}/reply`, { method: 'POST', body: { reply } });
}

/** 하나를 지운다 */
export function deleteInquiry(id: string): Promise<void> {
  return apiRequest<void>(`${ADMIN}/${id}`, { method: 'DELETE' });
}

/** 고른 것(ids) 또는 상자 하나(folder)를 지우고 지운 수를 돌려준다 */
export function deleteInquiries(target: { ids: string[] } | { folder: InquiryFolder }): Promise<number> {
  return apiRequest<Auth['schemas']['Deleted']>(`${ADMIN}/delete`, { method: 'POST', body: target }).then((answer) => answer.deleted);
}

/** 지운 일의 기록. 최근 것부터 한 쪽씩 */
export function fetchInquiryActions(before: string | undefined, signal?: AbortSignal): Promise<InquiryActionPage> {
  return apiRequest<InquiryActionPage>(`${ADMIN}/actions`, { query: { before }, ...(signal ? { signal } : {}) });
}
