// web/apps/web/src/format/visibility.test.ts
// 공개 범위의 글과 링크 공개(#993)의 주소.

import { describe, expect, it } from 'vitest';
import { shareAddress, visibilityShort } from './visibility';

describe('visibility', () => {
  it('공개 범위를 한 단어로 적는다', () => {
    expect([visibilityShort('private'), visibilityShort('public'), visibilityShort('unlisted')]).toEqual(['비공개', '공개', '링크 공개']);
  });

  it('나눌 주소는 이 사이트의 주소와 소개 화면의 경로다', () => {
    expect(shareAddress('https://example.com', '/chat/characters/c-1')).toBe('https://example.com/chat/characters/c-1');
  });
});
