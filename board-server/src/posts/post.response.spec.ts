// board-server/src/posts/post.response.spec.ts

/**
 * 글을 응답의 모양으로 바꾸는 함수들(post.response.ts)을 검증한다.
 */

import { toPostResponse, toPostSummaryResponse } from './post.response.js';

const POST = {
  id: '1234',
  authorId: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
  title: '첫 글',
  content: '본문입니다.',
  createdAt: new Date('2026-10-11T09:00:00.000Z'),
  updatedAt: new Date('2026-10-11T09:30:00.000Z'),
};

describe('toPostSummaryResponse', () => {
  it('목록의 한 줄에는 본문이 없다', () => {
    expect(toPostSummaryResponse(POST, 'free', 3)).toEqual({
      id: '1234',
      board: 'free',
      author_id: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
      title: '첫 글',
      comment_count: 3,
      created_at: '2026-10-11T09:00:00.000Z',
      updated_at: '2026-10-11T09:30:00.000Z',
    });
  });
});

describe('toPostResponse', () => {
  it('글 하나에는 본문이 있다', () => {
    expect(toPostResponse(POST, 'free', 3)).toEqual({
      id: '1234',
      board: 'free',
      author_id: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
      title: '첫 글',
      comment_count: 3,
      content: '본문입니다.',
      created_at: '2026-10-11T09:00:00.000Z',
      updated_at: '2026-10-11T09:30:00.000Z',
    });
  });

  it('글 번호는 글자로 내보낸다', () => {
    // JavaScript 의 숫자가 정확히 담지 못하는 크기의 번호
    const post = { ...POST, id: '9007199254740993' };

    expect(toPostResponse(post, 'free', 0).id).toBe('9007199254740993');
  });
});
