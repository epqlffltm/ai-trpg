// web/apps/web/src/pages/charge/ProductChoice.tsx
// 충전할 상품. 상품마다 단추 하나(값과 받을 골드). 누르면 그 상품으로 주문을 만든다.
// 값과 골드는 서버의 상품 목록 그대로다. 1원이 1크레딧이고 많이 산다고 더 주지 않는다(screens.md 의 A7).

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { walletProblemText } from '../wallet/walletProblem';
import { productsQuery } from './chargeQueries';
import { goldLabel, wonLabel } from './chargeView';

type Props = { busy: boolean; onChoose: (productId: string) => void };

export function ProductChoice({ busy, onChoose }: Props) {
  const products = useQuery(productsQuery());
  if (products.isPending) return <p aria-busy="true">상품을 불러오는 중</p>;
  if (products.isError) {
    return (
      <Notice tone="error">
        {walletProblemText(products.error)}{' '}
        <Button variant="quiet" onClick={() => void products.refetch()}>
          다시 시도
        </Button>
      </Notice>
    );
  }
  return (
    <ul className="plain-list products" aria-label="충전할 상품">
      {products.data.map((product) => (
        <li key={product.id}>
          <button type="button" className="product" disabled={busy} onClick={() => onChoose(product.id)}>
            <span className="product__gold">{goldLabel(product.credits)}</span>
            <span className="product__price">{wonLabel(product.price)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
