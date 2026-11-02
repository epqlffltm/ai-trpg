// web/apps/web/src/pages/trpg/studio/campaigns/CampaignNewPage.tsx
// 캠페인 만들기(#481 B, /trpg/studio/campaigns/new). 제목과 소개만 받고, 만들면 그 캠페인에서 편을 더한다.

import { createCampaign } from '../../../../api/campaigns';
import { CollectionNewPage } from '../collection/CollectionNewPage';

export function CampaignNewPage() {
  return <CollectionNewPage kind="campaigns" create={(body) => createCampaign({ ...body, episodes: [] })} />;
}
