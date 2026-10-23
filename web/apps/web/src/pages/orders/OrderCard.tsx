// web/apps/web/src/pages/orders/OrderCard.tsx
// 주문 하나. 값과 골드, 상태, 만든 때와 치른 때, 환불할 수 있는 기한, 할 수 없는 까닭.
// 할 수 있는 일은 상태가 정한다: 치렀고 철회할 수 있으면 청약철회(한 번 더 묻는다), 환불 처리 중이면 다시 확인.
// 결제 확인 중인 주문은 결제 번호를 이 화면이 모르므로 기다리게 한다(서버의 대사가 끝낸다).

import { Button } from '@ai-trpg/ui';
import { Link } from 'react-router';
import type { Order } from '../../api/types';
import { ConfirmButton } from '../../components/ConfirmButton';
import { ProblemNotice } from '../../components/ProblemNotice';
import { formatDateTime } from '../../format/dateTime';
import { failureText, goldAmount, goldLabel, wonLabel } from '../charge/chargeView';
import { blockedText, statusLabel } from './orderView';
import { useRefund } from './useRefund';

type Props = { order: Order; linkToDetail?: boolean };

export function OrderCard({ order, linkToDetail = false }: Props) {
  const refund = useRefund(order.id);
  const title = `${goldLabel(order.credits)} · ${wonLabel(order.price)}`;
  return (
    <article className={`order order--${order.status}`} aria-label={`주문 ${title}`}>
      <header className="order__head">
        <span className="order__title">{linkToDetail ? <Link to={`/wallet/orders/${order.id}`}>{title}</Link> : title}</span>
        <span className="order__status">{statusLabel(order.status)}</span>
      </header>
      <p className="hint order__when">
        주문 {formatDateTime(order.created_at)}
        {order.paid_at ? ` · 결제 ${formatDateTime(order.paid_at)}` : ''}
        {order.refunded_at ? ` · 환불 ${formatDateTime(order.refunded_at)}` : ''}
      </p>
      <OrderNote order={order} />
      {order.status === 'refunding' ? <ProblemNotice problem={refund.problem} /> : null}
      <OrderAction order={order} title={title} refund={refund} />
    </article>
  );
}

/** 상태마다 한 줄의 설명 */
function OrderNote({ order }: { order: Order }) {
  if (order.status === 'failed') return <p className="hint">{failureText(order.failure_code)} 돈은 나가지 않았습니다.</p>;
  if (order.status === 'confirming') return <p className="hint">결제 대행사의 결과를 기다립니다. 잠시 뒤 다시 보세요.</p>;
  if (order.status === 'refunding') return <p className="hint">골드는 이미 빠졌고, 돈이 돌아가는 중입니다.</p>;
  if (order.refundable && order.refundable_until) {
    return <p className="hint">{formatDateTime(order.refundable_until)}까지 청약철회할 수 있습니다(전액, 수수료 없음).</p>;
  }
  const blocked = blockedText(order);
  return blocked ? <p className="hint">{blocked}</p> : null;
}

function OrderAction({ order, title, refund }: { order: Order; title: string; refund: ReturnType<typeof useRefund> }) {
  if (order.status === 'refunding') {
    return (
      <Button variant="secondary" busy={refund.busy} onClick={() => void refund.refund()}>
        환불 다시 확인
      </Button>
    );
  }
  if (order.status !== 'paid' || !order.refundable) return null;
  return (
    <ConfirmButton
      label="청약철회"
      ariaLabel={`${title} 청약철회`}
      title="청약철회"
      confirm="환불하기"
      busy={refund.busy}
      problem={refund.problem}
      onConfirm={refund.refund}
      variant="secondary"
    >
      <p>
        {wonLabel(order.price)}을 돌려받고, 이 주문으로 받은 골드({goldAmount(order.credits)})가 지갑에서 빠집니다. 되돌릴 수 없습니다.
      </p>
    </ConfirmButton>
  );
}
