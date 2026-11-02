// web/apps/web/src/pages/trpg/studio/campaigns/CampaignEditPage.tsx
// 캠페인 하나(#481 B, /trpg/studio/campaigns/:campaignId). 제목과 소개를 고치고, 편을 고르고 차례를 정하고, 게시한다.
// 캠페인 자신은 CollectionEditPage 가 읽고, 편과 게시는 같은 열쇠의 읽기를 함께 쓴다(campaignQuery).

import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router';
import { fetchCampaign, updateCampaign } from '../../../../api/campaigns';
import { CollectionEditPage } from '../collection/CollectionEditPage';
import { campaignQuery } from './campaignQueries';
import { EpisodesSection } from './EpisodesSection';
import { PublishSection } from './PublishSection';

const CAMPAIGN_FROZEN = '이미 게시한 캠페인의 판은 게시할 때의 편과 시나리오의 판으로 굳어 있어, 여기서 고쳐도 바뀌지 않습니다. 다음에 게시하는 판부터 들어갑니다.';

export function CampaignEditPage() {
  const { campaignId = '' } = useParams();
  return (
    <CollectionEditPage
      kind="campaigns"
      assetId={campaignId}
      load={fetchCampaign}
      update={(body) => updateCampaign(campaignId, body)}
      frozenNote={CAMPAIGN_FROZEN}
    >
      <Campaign campaignId={campaignId} />
    </CollectionEditPage>
  );
}

function Campaign({ campaignId }: { campaignId: string }) {
  const campaign = useQuery(campaignQuery(campaignId));
  if (!campaign.data) return null;
  return (
    <>
      <EpisodesSection campaign={campaign.data} />
      <PublishSection campaignId={campaignId} />
    </>
  );
}
