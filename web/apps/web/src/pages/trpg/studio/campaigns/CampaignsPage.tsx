// web/apps/web/src/pages/trpg/studio/campaigns/CampaignsPage.tsx
// 내 캠페인 목록(#481 B, /trpg/studio/campaigns). 재료의 목록은 모양이 같다(AssetListPage).

import { AssetListPage } from '../AssetListPage';

export function CampaignsPage() {
  return <AssetListPage kind="campaigns" />;
}
