// web/apps/web/src/pages/trpg/campaigns/runQueries.ts
// 캠페인의 플레이(#481 B)를 읽는 것의 열쇠. 테이블의 열쇠(['trpg', 'tables', ...]) 아래에 두어,
// 테이블에 들어가거나 만들면(useEnterTable) 함께 다시 읽는다.
// 테이블 방에서는 다음 편을 기다리는 동안(방장이 열기 전) WAIT_POLL_MS 마다 다시 읽는다. 다음 편이 열렸다는 이벤트가 없어서다.

import { queryOptions } from '@tanstack/react-query';
import { fetchMyRuns, fetchRunOfTable } from '../../../api/campaignRuns';
import type { CampaignRun } from '../../../api/types';
import { episodeOfTable } from './runView';

/** 다음 편이 열리기를 기다리며 다시 읽는 사이 */
export const WAIT_POLL_MS = 15_000;

/** 로비 옆에 보이는 내 플레이의 수 */
export const RUNS_LIMIT = 6;

export function myRunsQuery() {
  return queryOptions({
    queryKey: ['trpg', 'tables', 'campaign-runs', { limit: RUNS_LIMIT }],
    queryFn: ({ signal }) => fetchMyRuns({ limit: RUNS_LIMIT, offset: 0 }, signal),
  });
}

/** 그 편이 끝났는데 다음 편의 테이블이 아직 없는가(방장이 열기를 기다린다) */
export function waitsForNext(run: CampaignRun | null | undefined, tableId: string, tableEnded: boolean): boolean {
  if (!run || !tableEnded || run.status !== 'playing') return false;
  const episode = episodeOfTable(run, tableId);
  const next = episode ? run.episodes[episode.position + 1] : undefined;
  return next !== undefined && next.table_id === null;
}

/** 그 테이블의 플레이. 그 편이 끝나 다음 편을 기다리는 동안 다시 읽는다 */
export function runOfTableQuery(tableId: string, tableEnded = false) {
  return queryOptions({
    queryKey: ['trpg', 'tables', tableId, 'campaign-run'],
    queryFn: ({ signal }) => fetchRunOfTable(tableId, signal),
    refetchInterval: (query) => (waitsForNext(query.state.data, tableId, tableEnded) ? WAIT_POLL_MS : false),
  });
}
