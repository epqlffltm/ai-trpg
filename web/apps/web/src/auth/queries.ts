// web/apps/web/src/auth/queries.ts
// 인증 서버에서 읽는 본인의 것(내 계정, 내 동의)의 열쇠와 부르는 함수. 머리, 마이페이지, 다시 동의가 함께 쓴다.

import { queryOptions } from '@tanstack/react-query';
import { fetchMyConsents } from '../api/account';
import { fetchMe } from '../api/auth';

export function meQuery() {
  return queryOptions({
    queryKey: ['auth', 'me'],
    queryFn: ({ signal }) => fetchMe(signal),
  });
}

export function myConsentsQuery() {
  return queryOptions({
    queryKey: ['auth', 'me', 'consents'],
    queryFn: ({ signal }) => fetchMyConsents(signal),
  });
}
