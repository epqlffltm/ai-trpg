// web/apps/web/src/pages/trpg/studio/campaigns/campaignQueries.ts
// 캠페인 고치기(#481 B)가 읽는 것. 캠페인 하나, 게시 점검, 판의 목록은 캠페인의 낱개 열쇠 아래에 둔다.
// 편을 저장하면 점검을 다시 읽고(캠페인은 받은 것으로 바꾼다), 게시하면 점검과 판의 목록을 다시 읽는다.

import { queryOptions } from '@tanstack/react-query';
import { fetchCampaign, fetchCampaignCheck, fetchCampaignVersions } from '../../../../api/campaigns';
import { assetDetailKey } from '../studioQueries';

export function campaignQuery(campaignId: string) {
  return queryOptions({
    queryKey: assetDetailKey('campaigns', campaignId),
    queryFn: ({ signal }) => fetchCampaign(campaignId, signal),
  });
}

export function campaignCheckKey(campaignId: string) {
  return [...assetDetailKey('campaigns', campaignId), 'publish-check'] as const;
}

export function campaignCheckQuery(campaignId: string) {
  return queryOptions({
    queryKey: campaignCheckKey(campaignId),
    queryFn: ({ signal }) => fetchCampaignCheck(campaignId, signal),
  });
}

export function campaignVersionsKey(campaignId: string) {
  return [...assetDetailKey('campaigns', campaignId), 'versions'] as const;
}

export function campaignVersionsQuery(campaignId: string) {
  return queryOptions({
    queryKey: campaignVersionsKey(campaignId),
    queryFn: ({ signal }) => fetchCampaignVersions(campaignId, signal),
  });
}
