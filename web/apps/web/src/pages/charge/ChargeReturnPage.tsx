// web/apps/web/src/pages/charge/ChargeReturnPage.tsx
// 토스페이먼츠의 결제창이 돌아오는 화면(A7, /wallet/charge/return). 로그인해야 열린다(App.tsx 의 RequireSession).
// 성공으로 돌아왔으면 승인을 요청하고 결과를 보인다. 실패로 돌아왔으면 까닭을 보이고 충전으로 돌려보낸다.
// 주소를 읽지 못했으면 서버에 아무것도 보내지 않는다(tossPayment.ts 의 readChargeReturn).

import { Button, Notice } from '@ai-trpg/ui';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { ProblemNotice } from '../../components/ProblemNotice';
import { ChargeResult } from './ChargeResult';
import { readChargeReturn, returnFailureText } from './tossPayment';
import { useChargeReturn } from './useChargeReturn';

export function ChargeReturnPage() {
  const [search] = useSearchParams();
  const result = readChargeReturn(search);
  return (
    <main className="page page--medium">
      <h1>충전</h1>
      {result.kind === 'paid' ? (
        <Confirming orderId={result.orderId} paymentKey={result.paymentKey} />
      ) : (
        <Notice tone="error">
          {result.kind === 'failed' ? returnFailureText(result.code) : '결제창의 결과를 읽지 못했습니다. 주문 내역에서 확인해 주세요.'}
        </Notice>
      )}
      {result.kind === 'paid' ? null : (
        <p>
          <Link to="/wallet/charge">충전으로</Link> · <Link to="/wallet/orders">주문 내역</Link>
        </p>
      )}
    </main>
  );
}

/** 결제 번호로 승인을 요청하고 결과를 보인다 */
function Confirming({ orderId, paymentKey }: { orderId: string; paymentKey: string }) {
  const charge = useChargeReturn(orderId, paymentKey);
  const navigate = useNavigate();
  if (!charge.order) {
    return (
      <>
        {charge.busy ? <p aria-busy="true">결제를 확인하는 중입니다.</p> : null}
        <ProblemNotice problem={charge.problem} />
        {charge.problem?.retry ? (
          <Button variant="secondary" busy={charge.busy} onClick={charge.retry}>
            다시 보내기
          </Button>
        ) : null}
        {charge.problem && !charge.problem.retry ? <Link to="/wallet/orders">주문 내역</Link> : null}
      </>
    );
  }
  return (
    <ChargeResult order={charge.order} busy={charge.busy} onRecheck={charge.retry} onRestart={() => void navigate('/wallet/charge')} />
  );
}
