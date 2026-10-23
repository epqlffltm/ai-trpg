// web/apps/web/src/pages/charge/ChargePage.tsx
// 충전(A7, /wallet/charge). 상품을 고르고 → 결제창에서 결제하고 → 결과를 본다. 지금은 테스트 모드다(돈이 나가지 않는다).
// 로그인해야 열린다(App.tsx 의 RequireSession). 결제할 수 있는지(본인인증, 보호자 동의)는 서버가 본다(403 을 알린다).
// 흐름과 다시 보내기는 useCharge 가, 결제창의 갈래는 paymentGateway 가 맡는다.

import { Button } from '@ai-trpg/ui';
import { Link } from 'react-router';
import { ProblemNotice } from '../../components/ProblemNotice';
import { ChargeResult } from './ChargeResult';
import { FakeCheckout } from './FakeCheckout';
import { gatewayKind } from './paymentGateway';
import { ProductChoice } from './ProductChoice';
import { useCharge, type Charge } from './useCharge';

export function ChargePage() {
  const charge = useCharge();
  return (
    <main className="page page--medium">
      <h1>충전</h1>
      <p className="hint">
        골드를 충전합니다. 지금은 테스트 모드라 실제 돈이 나가지 않습니다. <Link to="/wallet">지갑으로</Link>
      </p>
      <ProblemNotice problem={charge.problem} />
      {charge.problem?.retry ? (
        <Button variant="secondary" busy={charge.busy} onClick={charge.retry}>
          다시 보내기
        </Button>
      ) : null}
      <ChargeStep charge={charge} />
    </main>
  );
}

/** 지금 걸음의 화면. 주문이 없으면 상품, 결제 전이면 결제창, 그 뒤는 결과 */
function ChargeStep({ charge }: { charge: Charge }) {
  const { order } = charge;
  if (!order || charge.problem?.restart) {
    return (
      <section className="page-section" aria-labelledby="products-heading">
        <h2 id="products-heading">상품</h2>
        <ProductChoice busy={charge.busy} onChoose={(productId) => (charge.problem?.restart ? restartWith(charge, productId) : charge.choose(productId))} />
      </section>
    );
  }
  if (order.status === 'pending') {
    // 결제 번호를 한 번 보냈으면 결제창을 막는다. 답을 받지 못했어도 같은 번호로만 다시 보낸다(두 번 결제하지 않게)
    const locked = charge.busy || charge.paymentKey !== null;
    return gatewayKind() === 'fake' ? (
      <FakeCheckout order={order} busy={locked} onPaid={charge.pay} onCancel={charge.restart} />
    ) : (
      <p className="hint">결제창을 준비 중입니다.</p>
    );
  }
  return <ChargeResult order={order} busy={charge.busy} onRecheck={charge.retry} onRestart={charge.restart} />;
}

/** 처음부터 다시 해야 하는 실패 뒤에 상품을 고르면, 앞의 주문을 버리고 새로 시작한다 */
function restartWith(charge: Charge, productId: string) {
  charge.restart();
  charge.choose(productId);
}
