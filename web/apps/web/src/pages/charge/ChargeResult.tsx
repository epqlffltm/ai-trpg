// web/apps/web/src/pages/charge/ChargeResult.tsx
// 승인의 결과. 승인되면 지갑으로, 거절이나 만료면 처음부터, 모르면(confirming) 같은 결제 번호로 다시 확인한다.

import { Button, Notice } from '@ai-trpg/ui';
import { Link } from 'react-router';
import type { Order } from '../../api/types';
import { resultText } from './chargeView';

type Props = { order: Order; busy: boolean; onRecheck: () => void; onRestart: () => void };

export function ChargeResult({ order, busy, onRecheck, onRestart }: Props) {
  return (
    <section className="charge-result" aria-labelledby="charge-result-heading">
      <h3 id="charge-result-heading">결과</h3>
      <Notice tone={order.status === 'failed' || order.status === 'expired' ? 'error' : 'info'}>{resultText(order)}</Notice>
      <div className="checkout__outcomes">
        {order.status === 'confirming' ? (
          <Button variant="primary" busy={busy} onClick={onRecheck}>
            다시 확인
          </Button>
        ) : null}
        {order.status === 'paid' || order.status === 'confirming' ? <Link to="/wallet">지갑 보기</Link> : null}
        {order.status !== 'confirming' ? (
          <Button variant="secondary" disabled={busy} onClick={onRestart}>
            {order.status === 'paid' ? '더 충전하기' : '처음부터 다시'}
          </Button>
        ) : null}
      </div>
    </section>
  );
}
