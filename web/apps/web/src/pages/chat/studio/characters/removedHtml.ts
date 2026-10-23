// web/apps/web/src/pages/chat/studio/characters/removedHtml.ts
// 게시할 때 소개(HTML)에서 걸러 낸 것 하나를 글로. 순수한 함수다. 종류는 서버의 RemovedKind(asset-server/app/content/html.py)다.

import type { RemovedHtml } from '../../../../api/types';

const KIND_TEXT: Record<RemovedHtml['kind'], string> = {
  tag: '허용하지 않는 태그',
  attribute: '허용하지 않는 속성',
  style: '허용하지 않는 스타일',
  link: '허용하지 않는 링크',
  image: '허용하지 않는 그림',
};

export function removedLine(item: RemovedHtml): string {
  return `${KIND_TEXT[item.kind]}: ${item.name}`;
}
