// web/apps/web/src/pages/charge/useChargeReturn.ts
// 토스페이먼츠의 결제창에서 돌아온 뒤의 승인(A7). 주소에 실려 온 주문 번호와 결제 번호로 승인을 한 번 요청한다.
// 페이지를 떠났다 돌아왔으므로 useCharge 의 상태는 없다. 주문 번호와 결제 번호만으로 이어 간다.
//
//   - 처음 그릴 때 한 번 보낸다. 개발 빌드의 StrictMode 가 효과를 두 번 돌려도 한 번만 보낸다(sent).
//     막는 것은 쓸데없는 두 번째 요청뿐이다. 서버는 같은 결제 번호를 몇 번 받아도 한 번만 승인한다
//   - 답을 받지 못했거나 결과를 모르면(confirming) 같은 결제 번호로 다시 보낸다(retry)
//   - 답이 오면 주문 내역(A8)을, 승인되면 지갑도 다시 읽는다(useCharge 와 같다)

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { confirmOrder } from '../../api/orders';
import type { Order } from '../../api/types';
import { ORDERS_KEY } from '../orders/orderQueries';
import { WALLET_KEY } from '../wallet/walletQueries';
import { describeChargeProblem, type ChargeProblem } from './chargeProblem';

export type ChargeReturnState = {
  order: Order | null;
  busy: boolean;
  problem: ChargeProblem | undefined;
  retry: () => void;
};

export function useChargeReturn(orderId: string, paymentKey: string): ChargeReturnState {
  const queryClient = useQueryClient();
  const [order, setOrder] = useState<Order | null>(null);
  const [busy, setBusy] = useState(true);
  const [problem, setProblem] = useState<ChargeProblem | undefined>();
  const sent = useRef(false);

  async function confirm() {
    setBusy(true);
    setProblem(undefined);
    try {
      const next = await confirmOrder(orderId, paymentKey);
      setOrder(next);
      void queryClient.invalidateQueries({ queryKey: ORDERS_KEY });
      if (next.status === 'paid') void queryClient.invalidateQueries({ queryKey: WALLET_KEY });
    } catch (error) {
      setProblem(describeChargeProblem(error, 'confirm'));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    void confirm();
    // 처음 한 번만 보낸다. 다시 보내는 것은 retry 다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { order, busy, problem, retry: () => void confirm() };
}
