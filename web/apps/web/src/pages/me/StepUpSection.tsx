// web/apps/web/src/pages/me/StepUpSection.tsx
// 마이페이지의 "결제 본인 확인"(F5). 청약철회와 카드 등록·바꾸기·지우기 앞에서 메일 코드로 한 번 더 확인하는지를 보이고 켜고 끈다.
//   - 끄는 것은 이 세션의 창이 열린 동안에만 된다. 닫혀 있으면 인증 서버가 403 step_up_required 로 답하고, 확인 창을 띄운 뒤 다시 보낸다
//   - 켜는 것은 언제든 된다
//   - 끄면 카드 작업은 확인 없이 되고 청약철회는 하지 못한다(결제 서버가 정한다). 그래서 끄기 전에 그것을 알린다

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { setStepUpEnabled, type StepUpStatus } from '../../api/stepUp';
import { withStepUp } from '../../api/stepUpGate';
import type { FormProblem } from '../../auth/problem';
import { stepUpQuery } from '../../auth/queries';
import { describeStepUpProblem } from '../../auth/stepUpProblem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { formatDateTime } from '../../format/dateTime';
import { putQueryData } from '../../queryClient';

export function StepUpSection() {
  const status = useQuery(stepUpQuery());
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();

  async function change(enabled: boolean) {
    setBusy(true);
    setProblem(undefined);
    try {
      const next = await withStepUp(() => setStepUpEnabled(enabled));
      await putQueryData(queryClient, stepUpQuery().queryKey, next);
    } catch (error) {
      setProblem(describeStepUpProblem(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-section" aria-labelledby="step-up-heading">
      <h2 id="step-up-heading">결제 본인 확인</h2>
      {status.isPending ? <p>불러오는 중</p> : null}
      {status.isError ? (
        <Notice tone="error">
          본인 확인의 설정을 불러오지 못했습니다. <Button variant="quiet" onClick={() => void status.refetch()}>다시 시도</Button>
        </Notice>
      ) : null}
      {status.data ? <StepUpState status={status.data} busy={busy} onChange={(enabled) => void change(enabled)} /> : null}
      <ProblemNotice problem={problem} />
    </section>
  );
}

type StateProps = { status: StepUpStatus; busy: boolean; onChange: (enabled: boolean) => void };

function StepUpState({ status, busy, onChange }: StateProps) {
  if (!status.enabled) {
    return (
      <>
        <p>꺼져 있습니다. 카드 등록·바꾸기·지우기를 확인 없이 하고, 청약철회는 할 수 없습니다.</p>
        <Button variant="secondary" busy={busy} onClick={() => onChange(true)}>
          본인 확인 켜기
        </Button>
      </>
    );
  }
  return (
    <>
      <p>청약철회와 카드 등록·바꾸기·지우기 앞에서 가입한 메일로 받은 코드로 한 번 더 확인합니다.</p>
      {status.open && status.expires_at ? (
        <p className="hint">이 기기는 {formatDateTime(status.expires_at)}까지 다시 묻지 않습니다.</p>
      ) : null}
      <p className="hint">끄면 카드 작업은 확인 없이 되고, 청약철회는 다시 켤 때까지 할 수 없습니다. 끄려면 먼저 본인 확인을 합니다.</p>
      <Button variant="quiet" busy={busy} onClick={() => onChange(false)}>
        본인 확인 끄기
      </Button>
    </>
  );
}
