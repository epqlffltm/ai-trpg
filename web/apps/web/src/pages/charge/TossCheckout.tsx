// web/apps/web/src/pages/charge/TossCheckout.tsx
// 토스페이먼츠의 결제창으로 가는 단계(VITE_PAYMENT_GATEWAY=toss). 누르면 결제창을 현재 창에서 연다(tossPayment.ts).
// 결제를 마치면 토스페이먼츠가 돌아오는 화면(ChargeReturnPage)으로 보내고, 그 화면이 승인을 요청한다.
// 결제창을 열지 못했으면 까닭을 보이고 다시 누를 수 있다. 사용자가 닫았으면 아무것도 보이지 않는다.

import { Button, Notice } from '@ai-trpg/ui';
import { useState } from 'react';
import type { Order } from '../../api/types';
import { goldLabel, wonLabel } from './chargeView';
import { closedByUser, openTossPayment } from './tossPayment';

type Props = { order: Order; clientKey: string; onCancel: () => void };

export function TossCheckout({ order, clientKey, onCancel }: Props) {
  const [opening, setOpening] = useState(false);
  const [failed, setFailed] = useState(false);

  async function open() {
    setOpening(true);
    setFailed(false);
    try {
      await openTossPayment(clientKey, order);
    } catch (error) {
      if (!closedByUser(error)) setFailed(true);
    }
    // 열렸으면 이 페이지를 떠난다. 남아 있으면 닫았거나 열지 못한 것이다
    setOpening(false);
  }

  return (
    <section className="checkout" aria-labelledby="checkout-heading">
      <h3 id="checkout-heading">결제</h3>
      <p>
        {wonLabel(order.price)} · {goldLabel(order.credits)}
      </p>
      <p className="hint">토스페이먼츠의 결제창으로 갑니다. 결제를 마치면 이 화면으로 돌아옵니다.</p>
      {failed ? <Notice tone="error">결제창을 열지 못했습니다. 잠시 뒤에 다시 시도하세요.</Notice> : null}
      <div className="checkout__outcomes">
        <Button variant="primary" busy={opening} onClick={() => void open()}>
          결제하기
        </Button>
      </div>
      <Button variant="quiet" disabled={opening} onClick={onCancel}>
        다른 상품 고르기
      </Button>
    </section>
  );
}
