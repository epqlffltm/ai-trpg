// board-server/src/posts/post.response.spec.ts

/**
 * 글을 응답의 모양으로 바꾸는 함수들(post.response.ts)을 검증한다.
 */

import { toPostResponse, toPostSummaryResponse } from './post.response.js';

const NOW = new Date('2026-10-11T10:00:00.000Z');
const POST = {
  id: '1234',
  authorId: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
  title: '첫 글',
  content: '본문입니다.',
  pinnedUntil: null,
  createdAt: new Date('2026-10-11T09:00:00.000Z'),
  updatedAt: new Date('2026-10-11T09:30:00.000Z'),
};
const CONTEXT = {
  boardSlug: 'free',
  commentCount: 3,
  authorNickname: '모험가',
  now: NOW,
};

describe('toPostSummaryResponse', () => {
  it('목록의 한 줄에는 본문이 없다', () => {
    expect(toPostSummaryResponse(POST, CONTEXT)).toEqual({
      id: '1234',
      board: 'free',
      author_id: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
      author_nickname: '모험가',
      author_withdrawn: false,
      title: '첫 글',
      comment_count: 3,
      pinned: false,
      pinned_until: null,
      created_at: '2026-10-11T09:00:00.000Z',
      updated_at: '2026-10-11T09:30:00.000Z',
    });
  });

  it('고정된 글은 끝나는 시각과 함께 내보낸다', () => {
    const post = { ...POST, pinnedUntil: new Date('2026-10-18T09:00:00.000Z') };

    expect(toPostSummaryResponse(post, CONTEXT)).toMatchObject({
      pinned: true,
      pinned_until: '2026-10-18T09:00:00.000Z',
    });
  });

  it('고정이 끝난 글은 고정하지 않은 글로 내보낸다', () => {
    // 열에는 지난 시각이 남아 있다. 밖에서는 보이지 않는다
    const post = { ...POST, pinnedUntil: new Date('2026-10-11T09:59:59.999Z') };

    expect(toPostSummaryResponse(post, CONTEXT)).toMatchObject({
      pinned: false,
      pinned_until: null,
    });
  });
});

describe('글쓴이의 닉네임', () => {
  it('이름을 모르는 사람이면 null 이다', () => {
    expect(
      toPostSummaryResponse(POST, { ...CONTEXT, authorNickname: null })
        .author_nickname,
    ).toBeNull();
  });
});

describe('탈퇴한 글쓴이', () => {
  it('글쓴이가 비었으면 author_withdrawn 이 true 다. 이름을 모르는 사람과 가른다', () => {
    const withdrawn = { ...POST, authorId: null };

    expect(
      toPostSummaryResponse(withdrawn, { ...CONTEXT, authorNickname: null }),
    ).toMatchObject({
      author_id: null,
      author_nickname: null,
      author_withdrawn: true,
    });
    expect(
      toPostSummaryResponse(POST, { ...CONTEXT, authorNickname: null })
        .author_withdrawn,
    ).toBe(false);
  });
});

describe('toPostResponse', () => {
  it('글 하나에는 본문이 있다', () => {
    expect(toPostResponse(POST, CONTEXT)).toEqual({
      id: '1234',
      board: 'free',
      author_id: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
      author_nickname: '모험가',
      author_withdrawn: false,
      title: '첫 글',
      comment_count: 3,
      pinned: false,
      pinned_until: null,
      content: '본문입니다.',
      created_at: '2026-10-11T09:00:00.000Z',
      updated_at: '2026-10-11T09:30:00.000Z',
    });
  });

  it('글 번호는 글자로 내보낸다', () => {
    // JavaScript 의 숫자가 정확히 담지 못하는 크기의 번호
    const post = { ...POST, id: '9007199254740993' };

    expect(toPostResponse(post, CONTEXT).id).toBe('9007199254740993');
  });
});
