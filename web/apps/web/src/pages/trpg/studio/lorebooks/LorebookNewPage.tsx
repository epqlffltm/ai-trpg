// web/apps/web/src/pages/trpg/studio/lorebooks/LorebookNewPage.tsx
// 로어북 만들기(B9, /trpg/studio/lorebooks/new). 제목과 소개만 받고, 만들면 그 로어북에서 항목을 더한다.

import { createLorebook } from '../../../../api/lorebooks';
import { CollectionNewPage } from '../collection/CollectionNewPage';

export function LorebookNewPage() {
  return <CollectionNewPage kind="lorebooks" create={createLorebook} />;
}
