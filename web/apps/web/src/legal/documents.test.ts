// web/apps/web/src/legal/documents.test.ts
// 동의 항목이 가리키는 문서를 화면이 모두 갖는지, 문서에 작성자용의 글(검토할 것, 근거)이 섞이지 않았는지 본다.

import { describe, expect, it } from 'vitest';
import { consentDocumentName, itemsWithoutDocument } from './consentItems';
import { loadLegalDocument } from './documents';

const SERVER_ITEMS = [
  { item: 'terms', version: 1 },
  { item: 'privacy', version: 1 },
  { item: 'marketing', version: 1 },
  { item: 'ai_training', version: 1 },
];

describe('동의 문서', () => {
  it.each(SERVER_ITEMS)('$item 의 $version 판의 문서를 갖는다', async ({ item, version }) => {
    const name = consentDocumentName(item, version);
    expect(name).not.toBeNull();
    const text = await loadLegalDocument(name as string);
    expect(text.startsWith('# ')).toBe(true);
    expect(text).not.toContain('## 검토할 것');
    expect(text).not.toContain('## 근거');
  });

  it('화면이 갖지 않은 판을 가려낸다', () => {
    expect(itemsWithoutDocument([...SERVER_ITEMS, { item: 'terms', version: 9 }])).toEqual(['terms']);
  });

  it('없는 문서를 열면 오류다', async () => {
    await expect(loadLegalDocument('nothing-v1')).rejects.toThrow('화면에 없는 문서');
  });
});
