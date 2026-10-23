// web/apps/web/src/pages/trpg/room/round/CloseRoundButton.tsx
// 방장의 라운드 닫기(POST .../rounds/current/close, 202). 선언을 기다리지 않고 넘어가므로 한 번 더 묻는다.
// 서술에 실패해 멈춘 라운드에는 "서술 다시 맡기기"로 보인다(같은 주소, 판정은 다시 하지 않는다). 다른 모델로 몰래 바꾸지 않는다.

import { Button, Dialog } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { closeRound } from '../../../../api/rounds';
import type { Round } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { replaceCurrentRound, roundsKey } from './roundQueries';
import { describeCloseProblem, type RoundProblem } from './roundProblem';

export function CloseRoundButton({ tableId, round }: { tableId: string; round: Round }) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<RoundProblem | undefined>();
  const retry = round.status === 'closing';
  const close = useCallback(() => setAsking(false), []);

  async function send() {
    setBusy(true);
    setProblem(undefined);
    try {
      await replaceCurrentRound(queryClient, tableId, await closeRound(tableId));
      setAsking(false);
    } catch (error) {
      const next = describeCloseProblem(error);
      setProblem(next);
      if (next.refresh) void queryClient.invalidateQueries({ queryKey: roundsKey(tableId) });
    }
    setBusy(false);
  }

  if (retry) {
    return (
      <div className="round-host">
        <ProblemNotice problem={problem} />
        <Button variant="secondary" busy={busy} onClick={send}>
          서술 다시 맡기기
        </Button>
      </div>
    );
  }
  return (
    <div className="round-host">
      <Button variant="secondary" onClick={() => setAsking(true)}>
        라운드 닫기
      </Button>
      <Dialog title="라운드 닫기" open={asking} onClose={close}>
        <p>선언하지 않은 사람을 기다리지 않고 이 라운드를 마감합니다. 낸 선언의 판정을 하고 결과를 서술합니다.</p>
        <ProblemNotice problem={problem} />
        <div className="actions">
          <Button busy={busy} onClick={send}>
            마감하기
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
