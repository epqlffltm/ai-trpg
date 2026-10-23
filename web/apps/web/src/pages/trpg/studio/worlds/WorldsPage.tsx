// web/apps/web/src/pages/trpg/studio/worlds/WorldsPage.tsx
// 내 세계관 목록(B9, /trpg/studio/worlds). 재료의 목록은 모양이 같다(AssetListPage). 로그인해야 열린다.

import { AssetListPage } from '../AssetListPage';

export function WorldsPage() {
  return <AssetListPage kind="worlds" />;
}
