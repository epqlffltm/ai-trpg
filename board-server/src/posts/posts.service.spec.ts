// board-server/src/posts/posts.service.spec.ts

/**
 * 글 서비스의 순수한 함수(posts.service.ts 의 hasChanges)를 검증한다.
 * DB 를 쓰는 일은 test/posts.e2e-spec.ts 가 실제 PostgreSQL 에서 본다.
 */

import { hasChanges } from './posts.service.js';

describe('hasChanges', () => {
  it('칸이 하나라도 있으면 고칠 것이 있다', () => {
    expect(hasChanges({ title: '새 제목' })).toBe(true);
    expect(hasChanges({ content: '새 본문' })).toBe(true);
    expect(hasChanges({ title: '새 제목', content: '새 본문' })).toBe(true);
  });

  it('칸이 없으면 고칠 것이 없다', () => {
    expect(hasChanges({})).toBe(false);
    expect(hasChanges({ title: undefined, content: undefined })).toBe(false);
  });
});
