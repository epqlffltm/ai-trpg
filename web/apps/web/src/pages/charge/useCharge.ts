// web/apps/web/src/pages/charge/useCharge.ts
// 충전의 흐름(A7). 상품을 고르면 주문을 만들고(pending), 결제창이 준 결제 번호로 승인을 요청한다.
// 결제창이 무엇인지(가짜, 토스)는 모른다. 결제 번호만 받는다(paymentGateway.ts).
//
//   - 주문의 열쇠(Idempotency-Key)는 주문마다 새로 짓고, 답을 받지 못해 다시 보낼 때만 앞의 것을 쓴다(orderKey)
//   - 승인은 한 번에 하나만 보낸다(busy). 답을 받지 못했으면 같은 결제 번호로 다시 보낸다. 크레딧은 한 번만 들어간다
//   - 결과를 모르면(confirming) 실패로 보이지 않는다. "다시 확인"은 같은 결제 번호로 다시 부른다(서버가 결제 대행사에 묻는다)
//   - 승인되면 지갑(잔액과 원장)을 다시 읽는다

import { useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { confirmOrder, createOrder } from '../../api/orders';
import type { Order } from '../../api/types';
import { WALLET_KEY } from '../wallet/walletQueries';
import { describeChargeProblem, type ChargeProblem } from './chargeProblem';
import { orderKey } from './chargeView';

type Pending = { productId: string; key: string };

export type Charge = {
  order: Order | null;
  /** 승인을 요청한 결제 번호. 다시 확인할 때 같은 것을 쓴다 */
  paymentKey: string | null;
  busy: boolean;
  problem: ChargeProblem | undefined;
  choose: (productId: string) => void;
  pay: (paymentKey: string) => void;
  retry: () => void;
  restart: () => void;
};

function newKey(): string {
  return crypto.randomUUID();
}

export function useCharge(): Charge {
  const queryClient = useQueryClient();
  const [order, setOrder] = useState<Order | null>(null);
  const [paymentKey, setPaymentKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ChargeProblem | undefined>();
  const pending = useRef<Pending | null>(null);

  /** 한 걸음을 보낸다. 실패하면 할 일을 정하고, 다시 보낼 수 없으면 기억한 열쇠를 버린다 */
  async function step(stage: 'order' | 'confirm', send: () => Promise<void>) {
    setBusy(true);
    setProblem(undefined);
    try {
      await send();
    } catch (error) {
      const next = describeChargeProblem(error, stage);
      if (!next.retry) pending.current = null;
      setProblem(next);
    } finally {
      setBusy(false);
    }
  }

  function settle(next: Order) {
    setOrder(next);
    if (next.status === 'paid') void queryClient.invalidateQueries({ queryKey: WALLET_KEY });
  }

  function choose(productId: string) {
    const key = orderKey(pending.current, productId, newKey);
    pending.current = { productId, key };
    void step('order', async () => {
      const made = await createOrder(productId, key);
      pending.current = null;
      setPaymentKey(null);
      setOrder(made);
    });
  }

  function pay(key: string) {
    if (!order) return;
    const orderId = order.id;
    setPaymentKey(key);
    void step('confirm', async () => settle(await confirmOrder(orderId, key)));
  }

  /** 답을 받지 못한 걸음을 같은 열쇠나 같은 결제 번호로 다시 보낸다. 결과를 모르는 승인도 같다 */
  function retry() {
    if (order && paymentKey) return pay(paymentKey);
    if (pending.current) choose(pending.current.productId);
  }

  function restart() {
    pending.current = null;
    setOrder(null);
    setPaymentKey(null);
    setProblem(undefined);
  }

  return { order, paymentKey, busy, problem, choose, pay, retry, restart };
}
