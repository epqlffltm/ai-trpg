// board-server/src/posts/posts.policy.spec.ts

/**
 * 글에 관한 권한의 규칙(posts.policy.ts)을 검증한다.
 */

import {
  canDelete,
  canEdit,
  canWrite,
  isAuthor,
  isOperatorOnly,
} from './posts.policy.js';

const AUTHOR = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const SOMEONE = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';
const POST = { authorId: AUTHOR };
const MEMBER_BOARD = { writePolicy: 'member' } as const;
const OPERATOR_BOARD = { writePolicy: 'operator' } as const;

describe('isOperatorOnly', () => {
  it('운영자만 쓰는 게시판을 가린다', () => {
    expect(isOperatorOnly(OPERATOR_BOARD)).toBe(true);
    expect(isOperatorOnly(MEMBER_BOARD)).toBe(false);
  });
});

describe('canWrite', () => {
  it('누구나 쓰는 게시판에는 운영자가 아니어도 쓴다', () => {
    expect(canWrite(MEMBER_BOARD, false)).toBe(true);
    expect(canWrite(MEMBER_BOARD, true)).toBe(true);
  });

  it('운영자만 쓰는 게시판에는 운영자만 쓴다', () => {
    expect(canWrite(OPERATOR_BOARD, true)).toBe(true);
    expect(canWrite(OPERATOR_BOARD, false)).toBe(false);
  });
});

describe('isAuthor', () => {
  it('글쓴이를 가린다', () => {
    expect(isAuthor(POST, AUTHOR)).toBe(true);
    expect(isAuthor(POST, SOMEONE)).toBe(false);
  });
});

describe('canEdit', () => {
  it('글쓴이만 고친다', () => {
    expect(canEdit(POST, AUTHOR)).toBe(true);
    expect(canEdit(POST, SOMEONE)).toBe(false);
  });
});

describe('canDelete', () => {
  it('글쓴이는 운영자가 아니어도 지운다', () => {
    expect(canDelete(POST, AUTHOR, false)).toBe(true);
  });

  it('운영자는 남의 글도 지운다', () => {
    expect(canDelete(POST, SOMEONE, true)).toBe(true);
  });

  it('글쓴이도 운영자도 아니면 지우지 못한다', () => {
    expect(canDelete(POST, SOMEONE, false)).toBe(false);
  });
});
