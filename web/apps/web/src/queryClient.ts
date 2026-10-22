// web/apps/web/src/queryClient.ts
// 읽기(TanStack Query)의 기본값. 4xx 는 다시 불러도 같으므로 다시 시도하지 않고, 그 밖(5xx, 연결 끊김)은 한 번만 더 해 본다.
// 창에 돌아올 때마다 다시 부르지 않는다. 목록은 30초 동안 새것으로 본다.

import { QueryClient } from '@tanstack/react-query';
import { isClientError } from './api/http';

const MAX_RETRIES = 1;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => !isClientError(error) && failureCount < MAX_RETRIES,
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
    },
  });
}
