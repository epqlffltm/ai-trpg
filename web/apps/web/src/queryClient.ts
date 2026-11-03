// web/apps/web/src/queryClient.ts
// 읽기(TanStack Query)의 기본값. 4xx 는 다시 불러도 같으므로 다시 시도하지 않고, 그 밖(5xx, 연결 끊김)은 한 번만 더 해 본다.
// 창에 돌아올 때마다 다시 부르지 않는다. 목록은 30초 동안 새것으로 본다.
// 바꾸는 요청의 답을 읽기에 넣을 때는 putQueryData 를 쓴다(그냥 setQueryData 하면 먼저 떠난 읽기가 덮는다).

import { QueryClient, type QueryKey, type Updater } from '@tanstack/react-query';
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

/** putQueryData 의 고를 것 */
export type PutOptions = {
  /**
   * 답이 그 읽기의 값 전체인가(기본 false). 그렇다면 멈춘 읽기를 다시 하지 않는다.
   * 답이 바뀐 뒤의 전체라서 다시 읽어도 더 가져올 것이 없다(테이블, 지금 라운드). GET 하나를 아낀다(#975).
   */
  whole?: boolean;
};

/**
 * 바꾸는 요청의 답을 그 읽기에 넣는다.
 *
 * 그 요청보다 먼저 떠나 아직 오는 중인 읽기는 바뀌기 전의 것이다. 그대로 두면 나중에 닿아 넣은 것을 덮는다
 * (느린 망에서 고친 것이 잠깐 되돌아간다). 그래서 먼저 멈추고 넣는다.
 * 멈춘 읽기가 있었으면 넣은 뒤에 다시 읽는다. 답이 일부만 고칠 때(updater) 그 읽기가 가져올 다른 새것을 잃지 않게 한다.
 * 답이 전체이면(options.whole) 다시 읽지 않는다.
 */
export async function putQueryData<T>(
  queryClient: QueryClient,
  queryKey: QueryKey,
  value: Updater<T | undefined, T | undefined>,
  options: PutOptions = {},
): Promise<void> {
  const reading = queryClient.isFetching({ queryKey, exact: true }) > 0;
  await queryClient.cancelQueries({ queryKey, exact: true });
  queryClient.setQueryData<T>(queryKey, value);
  if (reading && !options.whole) void queryClient.invalidateQueries({ queryKey, exact: true });
}
