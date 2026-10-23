// web/apps/web/src/pages/orders/useRefund.ts
// 주문 하나의 청약철회. 한 번에 하나만 보낸다. 끝나면(환불됨, 처리 중) 그 주문을 바로 바꾸고 목록과 지갑을 다시 읽는다.
// 처리 중(refunding)이면 같은 주소를 다시 불러 같은 취소를 다시 보낸다(서버가 한 번만 취소한다).

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { refundOrder } from '../../api/orders';
import type { Order } from '../../api/types';
import { WALLET_KEY } from '../wallet/walletQueries';
import { ORDERS_KEY, orderQuery } from './orderQueries';
import { describeRefundProblem, type RefundProblem } from './refundProblem';

export type Refund = { busy: boolean; problem: RefundProblem | undefined; refund: () => Promise<boolean> };

export function useRefund(orderId: string): Refund {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<RefundProblem | undefined>();

  function refreshAfter(changed: Order | null) {
    if (changed) queryClient.setQueryData(orderQuery(orderId).queryKey, changed);
    void queryClient.invalidateQueries({ queryKey: ORDERS_KEY });
    void queryClient.invalidateQueries({ queryKey: WALLET_KEY });
  }

  /** 보낸다. 끝났으면(환불됨이든 처리 중이든) true. 실패하면 까닭을 남기고 false */
  async function refund(): Promise<boolean> {
    if (busy) return false;
    setBusy(true);
    setProblem(undefined);
    try {
      refreshAfter(await refundOrder(orderId));
      return true;
    } catch (error) {
      const next = describeRefundProblem(error);
      setProblem(next);
      if (next.refresh) refreshAfter(null);
      return false;
    } finally {
      setBusy(false);
    }
  }

  return { busy, problem, refund };
}
