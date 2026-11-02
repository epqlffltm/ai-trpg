// web/apps/web/src/pages/trpg/campaigns/useRunActions.ts
// 캠페인의 플레이를 시작하고, 다음 편을 열고, 다음 편에 들어간다(#481 B). 되면 그 편의 테이블 방으로 간다(useEnterTable).
// 다음 편에 이미 앉아 있으면(409 already_seated) 실패로 보이지 않고 그 테이블로 간다.

import { useState } from 'react';
import { joinRun, openNextEpisode, startRun } from '../../../api/campaignRuns';
import type { CampaignRun, CampaignRunTable } from '../../../api/types';
import type { FormProblem } from '../../../auth/problem';
import { useSending } from '../studio/useSending';
import { useEnterTable } from '../tables/useEnterTable';
import { describeJoinNextProblem, describeOpenNextProblem, describeStartProblem } from './runProblem';

/** 플레이의 지금 편의 테이블. 열지 않았으면 null */
export function currentTableId(run: CampaignRun): string | null {
  return run.episodes[run.position]?.table_id ?? null;
}

export function useStartRun(campaignId: string) {
  const sending = useSending();
  const enter = useEnterTable();

  async function start(table: CampaignRunTable): Promise<void> {
    const run = await sending.send(() => startRun(campaignId, table), describeStartProblem);
    const tableId = run ? currentTableId(run) : null;
    if (tableId) enter(tableId);
  }

  return { busy: sending.busy, problem: sending.problem, start };
}

export function useOpenNext(runId: string) {
  const sending = useSending();
  const enter = useEnterTable();

  async function open(table: CampaignRunTable): Promise<void> {
    const run = await sending.send(() => openNextEpisode(runId, table), describeOpenNextProblem);
    const tableId = run ? currentTableId(run) : null;
    if (tableId) enter(tableId);
  }

  return { busy: sending.busy, problem: sending.problem, open };
}

export function useJoinNext(runId: string) {
  const enter = useEnterTable();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>(undefined);

  /** 들어간다. 이미 앉아 있으면 tableId 로 간다 */
  async function join(tableId: string): Promise<void> {
    if (busy) return;
    setBusy(true);
    setProblem(undefined);
    try {
      enter((await joinRun(runId)).id);
    } catch (error) {
      const described = describeJoinNextProblem(error);
      if (described.seated) enter(tableId);
      else setProblem(described);
    } finally {
      setBusy(false);
    }
  }

  return { busy, problem, join };
}
