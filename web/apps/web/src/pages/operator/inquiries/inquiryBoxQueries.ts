// web/apps/web/src/pages/operator/inquiries/inquiryBoxQueries.ts
// 운영자 문의함의 읽기. 지우거나 답하면 ADMIN_INQUIRIES_KEY 아래를 모두 다시 읽는다(목록, 수, 하나, 기록).

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { fetchAdminInquiries, fetchAdminInquiry, fetchInquiryActions } from '../../../api/inquiryAdmin';

export const ADMIN_INQUIRIES_KEY = ['auth', 'admin', 'inquiries'] as const;

/** 상자 하나의 목록. status 가 없으면 모두 */
export function adminInquiriesQuery(status: 'open' | 'answered' | undefined) {
  return infiniteQueryOptions({
    queryKey: [...ADMIN_INQUIRIES_KEY, 'list', status ?? 'all'],
    queryFn: ({ pageParam, signal }) => fetchAdminInquiries(status, pageParam, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_before ?? undefined,
  });
}

/** 문의 하나. 처음 열면 서버가 읽음으로 적는다 */
export function adminInquiryQuery(id: string) {
  return queryOptions({
    queryKey: [...ADMIN_INQUIRIES_KEY, 'one', id],
    queryFn: ({ signal }) => fetchAdminInquiry(id, signal),
  });
}

/** 지운 일의 기록 */
export function inquiryActionsQuery() {
  return infiniteQueryOptions({
    queryKey: [...ADMIN_INQUIRIES_KEY, 'actions'],
    queryFn: ({ pageParam, signal }) => fetchInquiryActions(pageParam, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_before ?? undefined,
  });
}
