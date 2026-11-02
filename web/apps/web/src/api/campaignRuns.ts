// web/apps/web/src/api/campaignRuns.ts
// 게임 서버의 캠페인의 플레이(#481 B). 캠페인의 판 하나로 편마다 테이블을 차례로 연다.
//
// 답(trpg-server/app/campaigns/router.py):
//   - 시작과 다음 편: 테이블을 여는 실패는 테이블 만들기와 같다(403 adult_content_required, 422, 503)
//   - 409 reason episode_not_ended: 앞 편이 끝나지 않았다. run_ended: 마지막 편까지 끝났다
//   - 403(다음 편): 방장이 아니다
//   - 들어가기: 앉는 실패는 테이블에 들어가기와 같다(409 already_seated, table_full, not_recruiting). 플레이의 사람이 아니면 404
//   - 테이블의 플레이: 캠페인의 테이블이 아니거나 볼 수 없으면 null

import { apiRequest } from './http';
import type { CampaignRun, CampaignRunPage, CampaignRunTable, TableDetail } from './types';

const RUNS = '/api/v1/game/campaign-runs';

function runPath(runId: string, rest = ''): string {
  return `${RUNS}/${encodeURIComponent(runId)}${rest}`;
}

/** 내 플레이의 한 쪽. 최근에 시작한 것부터 */
export function fetchMyRuns(page: { limit: number; offset: number }, signal?: AbortSignal): Promise<CampaignRunPage> {
  return apiRequest<CampaignRunPage>(RUNS, { query: page, ...(signal ? { signal } : {}) });
}

/** 그 테이블의 플레이. 캠페인의 테이블이 아니면 null */
export function fetchRunOfTable(tableId: string, signal?: AbortSignal): Promise<CampaignRun | null> {
  return apiRequest<CampaignRun | null>(`${RUNS}/of-table/${encodeURIComponent(tableId)}`, signal ? { signal } : {});
}

/** 내 캠페인의 마지막 판으로 플레이를 시작한다. 첫 편의 테이블이 열리고 내가 방장이다 */
export function startRun(campaignId: string, table: CampaignRunTable): Promise<CampaignRun> {
  return apiRequest<CampaignRun>(RUNS, { method: 'POST', body: { campaign_id: campaignId, table } });
}

/** 방장이 다음 편의 테이블을 연다. 넘긴 캐릭터가 있으면 그것으로 앉는다 */
export function openNextEpisode(runId: string, table: CampaignRunTable): Promise<CampaignRun> {
  return apiRequest<CampaignRun>(runPath(runId, '/next'), { method: 'POST', body: table });
}

/** 플레이의 사람이 지금 편의 테이블에 초대 코드 없이 앉는다 */
export function joinRun(runId: string): Promise<TableDetail> {
  return apiRequest<TableDetail>(runPath(runId, '/join'), { method: 'POST' });
}
