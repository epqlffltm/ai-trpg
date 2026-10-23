// web/apps/web/src/pages/orders/OrdersPage.tsx
// 주문 내역(A8, /wallet/orders). 만든 때가 늦은 것부터, 한 쪽씩(더 보기). 로그인해야 열린다(App.tsx 의 RequireSession).
// 처음에는 결제가 일어난 주문만 보인다. 결제창만 열고 끝낸 것(결제 전, 시간이 지남)은 "치르지 않은 주문도 보기"로 연다.
// 거른 쪽이 비어도 더 읽을 쪽이 있으면 "더 보기"는 남는다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { walletProblemText } from '../wallet/walletProblem';
import { OrderCard } from './OrderCard';
import { ordersQuery } from './orderQueries';
import { hiddenCount, visibleOrders } from './orderView';

export function OrdersPage() {
  const query = useInfiniteQuery(ordersQuery());
  const [showAll, setShowAll] = useState(false);
  const all = query.data?.pages.flatMap((page) => page.orders) ?? [];
  const orders = visibleOrders(all, showAll);
  const hidden = hiddenCount(all);
  return (
    <main className="page page--medium">
      <h1>주문 내역</h1>
      <p className="hint">
        충전한 주문입니다. 결제한 지 7일 안이고 그 주문의 골드를 쓰지 않았으면 청약철회(전액 환불)할 수 있습니다. <Link to="/wallet">지갑으로</Link>
      </p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? (
        <Notice tone="error">
          {walletProblemText(query.error)}{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && orders.length === 0 && !query.hasNextPage ? (
        <div className="empty-state">
          <p>{all.length === 0 ? '아직 주문이 없습니다.' : '결제한 주문이 없습니다.'}</p>
          <Link to="/wallet/charge">충전하기</Link>
        </div>
      ) : null}
      {hidden > 0 || showAll ? (
        <label className="orders__toggle">
          <input type="checkbox" checked={showAll} onChange={(event) => setShowAll(event.target.checked)} /> 치르지 않은 주문도 보기
          {hidden > 0 ? <span className="hint"> ({hidden}개)</span> : null}
        </label>
      ) : null}
      <ul className="plain-list orders" aria-label="주문">
        {orders.map((order) => (
          <li key={order.id}>
            <OrderCard order={order} linkToDetail />
          </li>
        ))}
      </ul>
      {query.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            더 보기
          </Button>
        </div>
      ) : null}
    </main>
  );
}
