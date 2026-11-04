// web/apps/web/src/components/OrderChips.tsx
// 공개 목록의 차례 고르기(#985). 최신순과 인기순 가운데 하나다. 고른 것을 다시 눌러도 최신순으로 돌아간다.

import { ChipGroup } from '@ai-trpg/ui';
import type { ListingOrder } from '../api/listingOrder';

const ORDER_CHIPS: { value: ListingOrder; label: string }[] = [
  { value: 'recent', label: '최신순' },
  { value: 'popular', label: '인기순' },
];

type Props = { order: ListingOrder; onChange: (next: ListingOrder) => void };

export function OrderChips({ order, onChange }: Props) {
  return <ChipGroup<ListingOrder> label="차례" chips={ORDER_CHIPS} selected={order} onChange={(next) => onChange(next ?? 'recent')} />;
}
