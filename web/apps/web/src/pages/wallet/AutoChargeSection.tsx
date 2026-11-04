// web/apps/web/src/pages/wallet/AutoChargeSection.tsx
// 지갑(A6)의 자동 충전(#980). 카드(CardPanel)와 설정(AutoChargeForm)을 묶고, 서버에 보내고, 되지 않은 까닭을 보인다.
// 설정을 적으면 서버가 돌려준 것을 그대로 넣는다(putQueryData). 카드를 등록하거나 지우면 다시 읽는다(서버가 설정도 바꿀 수 있다).
// 상품 목록은 충전(A7)과 같은 것을 쓴다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { createCustomerKey, registerCard, removeCard, saveAutoCharge, type AutoChargeSettings } from '../../api/autoCharge';
import type { AutoCharge } from '../../api/types';
import { putQueryData } from '../../queryClient';
import { productsQuery } from '../charge/chargeQueries';
import { gatewayKind } from '../charge/paymentGateway';
import { AutoChargeForm } from './AutoChargeForm';
import { describeAutoChargeProblem, type AutoChargeProblem } from './autoChargeProblem';
import { AUTO_CHARGE_KEY, autoChargeQuery } from './autoChargeQueries';
import { CardPanel } from './CardPanel';
import { ProblemNotice } from './ProblemNotice';

export function AutoChargeSection() {
  const queryClient = useQueryClient();
  const current = useQuery(autoChargeQuery());
  const products = useQuery(productsQuery());
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<AutoChargeProblem | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function run(action: () => Promise<void>, doneText: string) {
    if (busy) return;
    setBusy(true);
    setProblem(null);
    setDone(null);
    try {
      await action();
      setDone(doneText);
    } catch (error) {
      setProblem(describeAutoChargeProblem(error));
    }
    setBusy(false);
  }

  const register = (authKey: string) =>
    run(async () => {
      await registerCard(authKey, await createCustomerKey());
      await queryClient.invalidateQueries({ queryKey: AUTO_CHARGE_KEY });
    }, '카드를 등록했습니다.');

  const remove = () =>
    run(async () => {
      await removeCard();
      await queryClient.invalidateQueries({ queryKey: AUTO_CHARGE_KEY });
    }, '카드를 지우고 자동 충전을 껐습니다.');

  const save = (settings: AutoChargeSettings) =>
    run(async () => {
      const saved = await saveAutoCharge(settings);
      await putQueryData<AutoCharge>(queryClient, AUTO_CHARGE_KEY, saved, { whole: true });
    }, settings.enabled ? '자동 충전을 켰습니다.' : '자동 충전 설정을 저장했습니다.');

  return (
    <section className="page-section auto-charge" aria-labelledby="auto-charge-heading">
      <h2 id="auto-charge-heading">자동 충전</h2>
      {current.isPending || products.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {current.isError || products.isError ? (
        <Notice tone="error">
          자동 충전을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void Promise.all([current.refetch(), products.refetch()])}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {done ? <Notice>{done}</Notice> : null}
      {problem ? <ProblemNotice problem={problem} /> : null}
      {current.data && products.data ? (
        <>
          <CardPanel card={current.data.card} gateway={gatewayKind()} busy={busy} onRegister={register} onRemove={remove} />
          <AutoChargeForm
            key={JSON.stringify(current.data.settings)}
            current={current.data}
            products={products.data}
            busy={busy}
            onSave={save}
          />
        </>
      ) : null}
    </section>
  );
}
