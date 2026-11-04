// web/apps/web/src/pages/wallet/useCardReturn.ts
// 토스페이먼츠의 카드 등록 창에서 돌아온 뒤의 등록(#980). 주소에 실려 온 인증 키와 고객 키로 카드를 한 번 등록한다.
//
//   - 처음 그릴 때 한 번 보낸다. 개발 빌드의 StrictMode 가 효과를 두 번 돌려도 한 번만 보낸다(sent)
//   - 다시 보내지 않는다. 인증 키는 한 번 쓰면 끝이라, 답을 받지 못했으면(card.issuer_unavailable) 등록을 처음부터 다시 한다
//   - 다시 읽을 것은 없다. 등록 창에서 돌아오며 앱을 새로 받았고, 지갑으로 가면 그때 읽는다

import { useEffect, useRef, useState } from 'react';
import { registerCard } from '../../api/autoCharge';
import type { PaymentCard } from '../../api/types';
import { describeAutoChargeProblem, type AutoChargeProblem } from './autoChargeProblem';

export type CardReturnState = { card: PaymentCard | null; busy: boolean; problem: AutoChargeProblem | null };

export function useCardReturn(authKey: string, customerKey: string): CardReturnState {
  const [card, setCard] = useState<PaymentCard | null>(null);
  const [busy, setBusy] = useState(true);
  const [problem, setProblem] = useState<AutoChargeProblem | null>(null);
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    registerCard(authKey, customerKey)
      .then(setCard)
      .catch((error: unknown) => setProblem(describeAutoChargeProblem(error)))
      .finally(() => setBusy(false));
  }, [authKey, customerKey]);

  return { card, busy, problem };
}
