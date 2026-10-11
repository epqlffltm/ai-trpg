// board-server/src/comments/comments.policy.spec.ts

/**
 * 댓글에 관한 규칙(comments.policy.ts)을 검증한다.
 */

import {
  canDelete,
  canEdit,
  canHaveReplies,
  hasRoomForReply,
  isAuthor,
  isReply,
  MAX_REPLIES_PER_COMMENT,
} from './comments.policy.js';

const AUTHOR = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const SOMEONE = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';
const COMMENT = { authorId: AUTHOR };

describe('isReply', () => {
  it('어느 댓글에 단 것이면 답글이다', () => {
    expect(isReply({ parentId: '57' })).toBe(true);
    expect(isReply({ parentId: null })).toBe(false);
  });
});

describe('canHaveReplies', () => {
  it('글에 단 댓글에는 답글을 단다', () => {
    expect(canHaveReplies({ parentId: null })).toBe(true);
  });

  it('답글에는 답글을 달지 못한다', () => {
    expect(canHaveReplies({ parentId: '57' })).toBe(false);
  });
});

describe('hasRoomForReply', () => {
  it('끝에 닿기 전까지는 자리가 있다', () => {
    expect(hasRoomForReply(0)).toBe(true);
    expect(hasRoomForReply(MAX_REPLIES_PER_COMMENT - 1)).toBe(true);
  });

  it('끝에 닿으면 자리가 없다', () => {
    expect(hasRoomForReply(MAX_REPLIES_PER_COMMENT)).toBe(false);
    expect(hasRoomForReply(MAX_REPLIES_PER_COMMENT + 1)).toBe(false);
  });
});

describe('isAuthor', () => {
  it('글쓴이를 가린다', () => {
    expect(isAuthor(COMMENT, AUTHOR)).toBe(true);
    expect(isAuthor(COMMENT, SOMEONE)).toBe(false);
  });
});

describe('canEdit', () => {
  it('글쓴이만 고친다', () => {
    expect(canEdit(COMMENT, AUTHOR)).toBe(true);
    expect(canEdit(COMMENT, SOMEONE)).toBe(false);
  });
});

describe('canDelete', () => {
  it('글쓴이는 운영자가 아니어도 지운다', () => {
    expect(canDelete(COMMENT, AUTHOR, false)).toBe(true);
  });

  it('운영자는 남의 댓글도 지운다', () => {
    expect(canDelete(COMMENT, SOMEONE, true)).toBe(true);
  });

  it('글쓴이도 운영자도 아니면 지우지 못한다', () => {
    expect(canDelete(COMMENT, SOMEONE, false)).toBe(false);
  });
});
