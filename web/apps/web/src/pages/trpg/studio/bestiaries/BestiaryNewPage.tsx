// web/apps/web/src/pages/trpg/studio/bestiaries/BestiaryNewPage.tsx
// 몬스터 모음 만들기(B9, /trpg/studio/bestiaries/new). 제목과 소개만 받고, 만들면 그 모음에서 몬스터를 더한다.

import { createBestiary } from '../../../../api/bestiaries';
import { CollectionNewPage } from '../collection/CollectionNewPage';

export function BestiaryNewPage() {
  return <CollectionNewPage kind="bestiaries" create={createBestiary} />;
}
