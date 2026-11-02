// web/apps/web/src/pages/trpg/room/round/RevertRoundButton.tsx
// 방장의 바로 앞 라운드 되돌리기(POST .../rounds/current/revert, #288). 되돌리면 되돌릴 수 없으므로 한 번 더 묻는다.
// 지금 라운드가 선언을 받는 중이고 첫 라운드가 아니며 아무도 선언하지 않았을 때만 보인다. 되는지는 서버가 정한다
// (그 사이 다른 일이 있었으면 409). 되돌리면 같은 번호의 라운드가 그때의 장면과 선언으로 다시 열린다.
// 지난 라운드 목록도 버린다. 되돌린 라운드는 목록에서 빠진다.

import { Button, Dialog } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { revertRound } from '../../../../api/rounds';
import type { Round } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { replaceCurrentRound, roundHistoryKey, roundsKey } from './roundQueries';
import { describeRevertProblem, type RoundProblem } from './roundProblem';

/** 되돌리기 단추를 보일 라운드인가. 선언을 받는 중이고, 첫 라운드가 아니고, 아무도 선언하지 않았다 */
export function canOfferRevert(round: Round): boolean {
  return round.status === 'open' && round.number > 1 && round.declarations.length === 0;
}

export function RevertRoundButton({ tableId, round }: { tableId: string; round: Round }) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<RoundProblem | undefined>();
  const close = useCallback(() => setAsking(false), []);
  const previous = round.number - 1;

  async function send() {
    setBusy(true);
    setProblem(undefined);
    try {
      await replaceCurrentRound(queryClient, tableId, await revertRound(tableId));
      void queryClient.invalidateQueries({ queryKey: roundHistoryKey(tableId) });
      setAsking(false);
    } catch (error) {
      const next = describeRevertProblem(error);
      setProblem(next);
      if (next.refresh) void queryClient.invalidateQueries({ queryKey: roundsKey(tableId) });
    }
    setBusy(false);
  }

  return (
    <div className="round-host">
      <Button variant="quiet" onClick={() => setAsking(true)}>
        {previous} 라운드 되돌리기
      </Button>
      <Dialog title={`${previous} 라운드 되돌리기`} open={asking} onClose={close}>
        <p>
          {previous} 라운드를 닫기 직전으로 되돌립니다. 판정, HP, 물건, 퀘스트가 그때로 돌아가고 그때의 선언으로 같은 라운드를 다시
          진행합니다. 선언은 고칠 수 있고, 다시 닫으면 주사위를 새로 굴립니다.
        </p>
        <p className="hint">이미 낸 서술 값은 돌려주지 않습니다. 다시 닫으면 서술 값이 한 번 더 듭니다.</p>
        <ProblemNotice problem={problem} />
        <div className="actions">
          <Button busy={busy} onClick={send}>
            되돌리기
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
