// web/apps/web/src/pages/orders/orderQueries.ts
// 주문 내역(A8)이 읽는 것의 열쇠와 부르는 함수. 목록(한 쪽씩)과 주문 하나.
// 청약철회나 확인으로 주문이 바뀌면 ORDERS_KEY 를 무른다(목록과 주문 하나가 함께 다시 읽힌다).

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { fetchOrder, fetchOrders } from '../../api/orders';

export const ORDERS_KEY = ['billing', 'orders'] as const;

/** 내 주문. 만든 때가 늦은 것부터 한 쪽씩. 다음 쪽은 앞 쪽의 next_before, null 이면 끝이다 */
export function ordersQuery() {
  return infiniteQueryOptions({
    queryKey: [...ORDERS_KEY, 'list'],
    queryFn: ({ pageParam, signal }) => fetchOrders(pageParam, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_before ?? undefined,
  });
}

export function orderQuery(orderId: string) {
  return queryOptions({
    queryKey: [...ORDERS_KEY, 'one', orderId],
    queryFn: ({ signal }) => fetchOrder(orderId, signal),
  });
}
