// web/apps/web/src/pages/charge/FakeCheckout.tsx
// 시험용 결제창(VITE_PAYMENT_GATEWAY=fake). 결제 서버의 가짜 결제 대행사에 맞춘다. 돈이 오가지 않는다.
// 결과를 고르면 그 결과의 앞머리로 결제 번호를 지어 넘긴다(paymentGateway.ts 의 FAKE_OUTCOMES).
// 실제 결제창(토스페이먼츠)도 마지막에 결제 번호 하나를 넘긴다. 받는 쪽(useCharge)은 같다.

import { Button } from '@ai-trpg/ui';
import type { Order } from '../../api/types';
import { goldLabel, wonLabel } from './chargeView';
import { FAKE_OUTCOMES, fakePaymentKey } from './paymentGateway';

type Props = { order: Order; busy: boolean; onPaid: (paymentKey: string) => void; onCancel: () => void };

export function FakeCheckout({ order, busy, onPaid, onCancel }: Props) {
  return (
    <section className="checkout" aria-labelledby="checkout-heading">
      <h3 id="checkout-heading">시험용 결제창</h3>
      <p>
        {wonLabel(order.price)} · {goldLabel(order.credits)}
      </p>
      <p className="hint">실제 결제가 아닙니다. 결제의 결과를 골라 흐름을 봅니다.</p>
      <div className="checkout__outcomes">
        {FAKE_OUTCOMES.map((outcome) => (
          <Button
            key={outcome.prefix}
            variant={outcome.prefix === 'fake_ok_' ? 'primary' : 'secondary'}
            disabled={busy}
            onClick={() => onPaid(fakePaymentKey(outcome.prefix, crypto.randomUUID()))}
          >
            {outcome.label}
          </Button>
        ))}
      </div>
      <ul className="hint checkout__hints">
        {FAKE_OUTCOMES.map((outcome) => (
          <li key={outcome.prefix}>
            {outcome.label}: {outcome.hint}
          </li>
        ))}
      </ul>
      <Button variant="quiet" disabled={busy} onClick={onCancel}>
        다른 상품 고르기
      </Button>
    </section>
  );
}
