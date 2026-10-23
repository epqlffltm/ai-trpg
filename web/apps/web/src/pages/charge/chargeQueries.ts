// web/apps/web/src/pages/charge/chargeQueries.ts
// 충전(A7)이 읽는 상품의 열쇠와 부르는 함수. 상품은 자주 바뀌지 않는다. 화면을 열 때 읽는다.

import { queryOptions } from '@tanstack/react-query';
import { fetchProducts } from '../../api/orders';

export function productsQuery() {
  return queryOptions({
    queryKey: ['billing', 'products'],
    queryFn: ({ signal }) => fetchProducts(signal),
    staleTime: 5 * 60 * 1000,
  });
}
