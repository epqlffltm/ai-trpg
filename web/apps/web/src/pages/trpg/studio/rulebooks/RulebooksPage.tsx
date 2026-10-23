// web/apps/web/src/pages/trpg/studio/rulebooks/RulebooksPage.tsx
// 내 룰북 목록(B9, /trpg/studio/rulebooks). 재료의 목록은 모양이 같다(AssetListPage). 로그인해야 열린다.

import { AssetListPage } from '../AssetListPage';

export function RulebooksPage() {
  return <AssetListPage kind="rulebooks" />;
}
