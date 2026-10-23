// web/apps/web/src/pages/orders/OrderPage.tsx
// 주문 하나(A8, /wallet/orders/:orderId). 지갑의 원장 줄(order_id)에서 온다. 남의 주문이나 없는 주문은 서버가 같은 404 다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { isClientError } from '../../api/http';
import { walletProblemText } from '../wallet/walletProblem';
import { OrderCard } from './OrderCard';
import { orderQuery } from './orderQueries';

export function OrderPage() {
  const { orderId = '' } = useParams();
  const order = useQuery(orderQuery(orderId));
  return (
    <main className="page page--medium">
      <h1>주문</h1>
      <p className="hint">
        <Link to="/wallet/orders">주문 내역</Link> · <Link to="/wallet">지갑</Link>
      </p>
      {order.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {order.isError ? (
        isClientError(order.error) ? (
          <Notice tone="error">그런 주문이 없습니다.</Notice>
        ) : (
          <Notice tone="error">
            {walletProblemText(order.error)}{' '}
            <Button variant="quiet" onClick={() => void order.refetch()}>
              다시 시도
            </Button>
          </Notice>
        )
      ) : null}
      {order.data ? <OrderCard order={order.data} /> : null}
    </main>
  );
}
