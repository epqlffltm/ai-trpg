// web/apps/web/src/api/listingOrder.ts
// 공개 목록의 차례(#985). recent 는 최근에 공개한 것부터(서버의 기본), popular 는 최근 7일에 많이 시작한 것부터다.
// 주소의 ?sort=popular 와 오간다. 모르는 값은 기본으로 본다. 서버에는 popular 일 때만 싣는다.

export type ListingOrder = 'recent' | 'popular';

export function parseOrder(value: string | null): ListingOrder {
  return value === 'popular' ? 'popular' : 'recent';
}

/** 목록의 주소에 더할 값. 기본이면 싣지 않는다 */
export function orderQuery(order: ListingOrder | undefined): { sort?: string } {
  return order === 'popular' ? { sort: 'popular' } : {};
}
