// web/apps/web/src/pages/support/supportQueries.ts
// 내 문의의 읽기. 보내면 이 열쇠를 다시 읽는다.

import { infiniteQueryOptions } from '@tanstack/react-query';
import { fetchMyInquiries } from '../../api/inquiries';

export const MY_INQUIRIES_KEY = ['auth', 'me', 'inquiries'] as const;

export function myInquiriesQuery() {
  return infiniteQueryOptions({
    queryKey: MY_INQUIRIES_KEY,
    queryFn: ({ pageParam, signal }) => fetchMyInquiries(pageParam, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_before ?? undefined,
  });
}
