// web/apps/web/src/pages/wallet/AutoChargeSection.tsx
// 지갑(A6)의 자동 충전(#980). 카드(CardPanel)와 설정(AutoChargeForm)을 묶고, 서버에 보내고, 되지 않은 까닭을 보인다.
// 설정을 적으면 서버가 돌려준 것을 그대로 넣는다(putQueryData). 카드를 등록하거나 지우면 다시 읽는다(서버가 설정도 바꿀 수 있다).
// 상품 목록은 충전(A7)과 같은 것을 쓴다.
// 토스페이먼츠의 카드 등록 창(toss)은 고객 키를 받은 뒤 현재 창에서 연다. 창이 열리면 이 페이지를 떠나므로 마친 글을 보이지 않는다.
// 사용자가 창을 닫았으면 아무것도 보이지 않는다. 열지 못했으면 까닭을 보인다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { createCustomerKey, registerCard, removeCard, saveAutoCharge, type AutoChargeSettings } from '../../api/autoCharge';
import { ApiError, NetworkError } from '../../api/errors';
import type { AutoCharge } from '../../api/types';
import { putQueryData } from '../../queryClient';
import { productsQuery } from '../charge/chargeQueries';
import { gatewayKind, tossClientKey } from '../charge/paymentGateway';
import { closedByUser } from '../charge/tossPayment';
import { AutoChargeForm } from './AutoChargeForm';
import { describeAutoChargeProblem, type AutoChargeProblem } from './autoChargeProblem';
import { AUTO_CHARGE_KEY, autoChargeQuery } from './autoChargeQueries';
import { CardPanel } from './CardPanel';
import { ProblemNotice } from './ProblemNotice';
import { openTossCardRegistration } from './tossCard';

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

  async function openToss() {
    const clientKey = tossClientKey();
    if (busy || clientKey === null) return;
    setBusy(true);
    setProblem(null);
    setDone(null);
    try {
      await openTossCardRegistration(clientKey, await createCustomerKey());
    } catch (error) {
      if (!closedByUser(error)) setProblem(windowProblem(error));
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
          <CardPanel
            card={current.data.card}
            gateway={gatewayKind()}
            busy={busy}
            onRegister={register}
            onOpenToss={() => void openToss()}
            onRemove={remove}
          />
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

/** 카드 등록 창을 열지 못한 까닭. 서버의 답(고객 키)이면 서버의 까닭이고, 그 밖(SDK, 스크립트를 받지 못함)은 한 말이다 */
function windowProblem(error: unknown): AutoChargeProblem {
  if (error instanceof ApiError || error instanceof NetworkError) return describeAutoChargeProblem(error);
  return { message: '카드 등록 창을 열지 못했습니다. 잠시 뒤에 다시 시도하세요.', link: null };
}
