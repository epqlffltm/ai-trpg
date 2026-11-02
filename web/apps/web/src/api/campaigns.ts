// web/apps/web/src/api/campaigns.ts
// 게임 서버의 캠페인(#481 B, 제작 도구 B9). 내 시나리오 여러 편을 차례로 묶고, 게시하면 편마다 그때의 판이 굳는다.
// 목록과 지우기는 재료가 함께 쓴다(studio.ts).
//
// 답(trpg-server/app/assets/campaigns/router.py):
//   - 422 field episodes: 지웠거나 남의 시나리오를 편에 넣었다. 같은 시나리오를 두 번 넣어도 422 다
//   - 409 {problems}(게시): 게시할 조건을 갖추지 못했다. 게시 점검(publish-check)과 같은 이름들이다
//   - 403 code adult_content_required(게시): 성인용 편이 있는데 성인 확인을 하지 않았다

import { apiRequest } from './http';
import { assetPath, assetsPath } from './studio';
import type {
  CampaignCreate,
  CampaignDetail,
  CampaignPublishCheck,
  CampaignUpdate,
  CampaignVersionDetail,
  CampaignVersionSummary,
} from './types';

function campaignPath(campaignId: string, rest = ''): string {
  return `${assetPath('campaigns', campaignId)}${rest}`;
}

/** 캠페인 하나. 편을 차례대로 싣는다 */
export function fetchCampaign(campaignId: string, signal?: AbortSignal): Promise<CampaignDetail> {
  return apiRequest<CampaignDetail>(campaignPath(campaignId), signal ? { signal } : {});
}

export function createCampaign(body: CampaignCreate): Promise<CampaignDetail> {
  return apiRequest<CampaignDetail>(assetsPath('campaigns'), { method: 'POST', body });
}

/** 보낸 칸만 바뀐다. 편은 목록을 통째로 보낸다 */
export function updateCampaign(campaignId: string, body: CampaignUpdate): Promise<CampaignDetail> {
  return apiRequest<CampaignDetail>(campaignPath(campaignId), { method: 'PATCH', body });
}

/** 지금 게시하면 막히는 것(problems)과 알릴 것(warnings). 판을 만들지 않는다 */
export function fetchCampaignCheck(campaignId: string, signal?: AbortSignal): Promise<CampaignPublishCheck> {
  return apiRequest<CampaignPublishCheck>(campaignPath(campaignId, '/publish-check'), signal ? { signal } : {});
}

/** 지금의 편들을 새 판으로 굳힌다. 막히면 409 {problems} */
export function publishCampaign(campaignId: string, note: string): Promise<CampaignVersionDetail> {
  return apiRequest<CampaignVersionDetail>(campaignPath(campaignId, '/versions'), { method: 'POST', body: { note } });
}

/** 낸 판. 최근 것부터 */
export function fetchCampaignVersions(campaignId: string, signal?: AbortSignal): Promise<CampaignVersionSummary[]> {
  return apiRequest<CampaignVersionSummary[]>(campaignPath(campaignId, '/versions'), signal ? { signal } : {});
}
