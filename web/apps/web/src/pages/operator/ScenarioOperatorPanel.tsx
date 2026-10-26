// web/apps/web/src/pages/operator/ScenarioOperatorPanel.tsx
// 시나리오 소개(B2) 아래의 운영자 칸(E4, #392). 운영자에게만 보인다(토큰의 역할로 숨길 뿐이고, 서버가 다시 막는다).
//   - 이 판의 제재: 공개를 내리고 그 판은 다시 공개하지 못한다. 제작자는 고쳐서 새 판을 내면 다시 공개한다
//   - 제작자의 공개 금지와 풀기: 지금 금지 중인지 읽는 API 가 없어 두 단추를 다 두고, 맞지 않으면 서버의 409 를 알린다
// 제재해도 이 화면은 그대로 둔다(다시 읽으면 공개가 내려가 404 라 결과를 볼 수 없다). 탐색 목록만 다시 읽게 한다.

import { Notice } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { banPublisher, liftPublishingBan, sanctionScenario, type PublishingBan, type SanctionResult } from '../../api/gameOperator';
import type { PublicListingDetail } from '../../api/types';
import type { FormProblem } from '../../auth/problem';
import { ReasonConfirm } from './ReasonConfirm';
import { describeSanctionProblem } from './sanctionProblem';
import { banNotice, sanctionNotice } from './sanctionView';

type Props = { listing: PublicListingDetail; creatorName: string | undefined };

export function ScenarioOperatorPanel({ listing, creatorName }: Props) {
  const sanction = useSanctionCall((reason: string) => sanctionScenario(listing.scenario_id, reason));
  const ban = useSanctionCall((reason: string) => banPublisher(listing.creator_id, reason));
  const lift = useSanctionCall((reason: string) => liftPublishingBan(listing.creator_id, reason));
  const creator = creatorName ?? '제작자';

  return (
    <section className="page-section operator-panel" aria-labelledby="scenario-operator">
      <h2 id="scenario-operator">운영자</h2>
      <p className="hint">
        시나리오 id {listing.scenario_id} · 제작자 id {listing.creator_id}. 사유는 감사 기록에만 남고, 당사자에게는 제재된 것만 알립니다.
      </p>
      {sanction.result ? <Notice tone="info">{sanctionNotice(sanction.result)}</Notice> : null}
      {ban.result ? <Notice tone="info">{banNotice(ban.result, creator)}</Notice> : null}
      {lift.result ? <Notice tone="info">{banNotice(lift.result, creator)}</Notice> : null}
      <div className="actions">
        <ReasonConfirm label="이 판 제재하기" title={`${listing.version}판 제재`} confirm="제재하기" busy={sanction.busy} problem={sanction.problem} onSubmit={sanction.run}>
          <p>공개를 내리고 이 판은 다시 공개하지 못합니다. 이미 열린 테이블은 그대로입니다. 제재가 쌓이면 제작자는 저절로 공개 금지가 됩니다.</p>
        </ReasonConfirm>
        <ReasonConfirm label="제작자 공개 금지" title={`${creator}의 공개 금지`} confirm="공개 금지" busy={ban.busy} problem={ban.problem} onSubmit={ban.run}>
          <p>이 사람은 어떤 판도 공개하지 못합니다. 이미 공개 중인 다른 시나리오와 플레이는 그대로입니다.</p>
        </ReasonConfirm>
        <ReasonConfirm label="공개 금지 풀기" title={`${creator}의 공개 금지 풀기`} confirm="풀기" busy={lift.busy} problem={lift.problem} onSubmit={lift.run}>
          <p>다시 공개할 수 있게 됩니다. 그 뒤의 제재부터 다시 셉니다.</p>
        </ReasonConfirm>
      </div>
    </section>
  );
}

type SanctionCall<T> = { busy: boolean; problem: FormProblem | undefined; result: T | null; run: (reason: string) => Promise<boolean> };

/** 동작 하나의 바쁨, 실패, 결과. 성공하면 탐색 목록(공개가 바뀐다)을 다시 읽게 한다 */
function useSanctionCall<T extends SanctionResult | PublishingBan>(call: (reason: string) => Promise<T>): SanctionCall<T> {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const [result, setResult] = useState<T | null>(null);

  async function run(reason: string): Promise<boolean> {
    setBusy(true);
    setProblem(undefined);
    try {
      setResult(await call(reason));
      void queryClient.invalidateQueries({ queryKey: ['trpg', 'listings', 'browse'] });
      return true;
    } catch (error) {
      setProblem(describeSanctionProblem(error));
      return false;
    } finally {
      setBusy(false);
    }
  }

  return { busy, problem, result, run };
}
