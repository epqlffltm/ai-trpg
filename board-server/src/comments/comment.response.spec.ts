// board-server/src/comments/comment.response.spec.ts

/**
 * 댓글을 응답의 모양으로 바꾸는 함수들(comment.response.ts)을 검증한다.
 */

import { NO_NICKNAMES } from '../authors/nicknames.js';
import { Comment } from './comment.entity.js';
import {
  authorsOf,
  toCommentResponse,
  toCommentThreadResponse,
} from './comment.response.js';

const COMMENT = {
  id: '57',
  postId: '1234',
  parentId: null,
  authorId: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
  content: '댓글입니다.',
  createdAt: new Date('2026-10-11T09:00:00.000Z'),
  updatedAt: new Date('2026-10-11T09:30:00.000Z'),
  deletedAt: null,
};
const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const REPLIER = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';
/** 글쓴이의 이름만 아는 표 */
const NICKNAMES = new Map([[WRITER, '모험가']]);

describe('toCommentResponse', () => {
  it('댓글을 밑줄로 이은 칸 이름과 글자 번호로 내보낸다', () => {
    expect(toCommentResponse(COMMENT, NICKNAMES)).toEqual({
      id: '57',
      post_id: '1234',
      parent_id: null,
      author_id: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
      author_nickname: '모험가',
      content: '댓글입니다.',
      deleted: false,
      created_at: '2026-10-11T09:00:00.000Z',
      updated_at: '2026-10-11T09:30:00.000Z',
    });
  });

  it('답글은 어느 댓글에 단 것인지 알린다', () => {
    const reply = { ...COMMENT, id: '58', parentId: '57' };

    expect(toCommentResponse(reply, NICKNAMES).parent_id).toBe('57');
  });

  it('지운 댓글은 누가 무엇을 썼는지 내보내지 않는다', () => {
    const deleted = {
      ...COMMENT,
      deletedAt: new Date('2026-10-11T10:00:00.000Z'),
    };

    expect(toCommentResponse(deleted, NICKNAMES)).toMatchObject({
      id: '57',
      author_id: null,
      author_nickname: null,
      content: null,
      deleted: true,
    });
  });
});

describe('글쓴이의 닉네임', () => {
  it('이름을 모르는 사람이면 null 이다', () => {
    expect(toCommentResponse(COMMENT, NO_NICKNAMES).author_nickname).toBeNull();
  });
});

describe('toCommentThreadResponse', () => {
  it('댓글에 답글들을 붙여 내보낸다', () => {
    const reply = { ...COMMENT, id: '58', parentId: '57', content: '답글' };

    const response = toCommentThreadResponse(
      {
        comment: COMMENT as Comment,
        replies: [reply as Comment],
      },
      NICKNAMES,
    );

    expect(response).toMatchObject({ id: '57', content: '댓글입니다.' });
    expect(response.replies).toEqual([toCommentResponse(reply, NICKNAMES)]);
  });

  it('답글이 없으면 빈 목록이다', () => {
    const response = toCommentThreadResponse(
      {
        comment: COMMENT as Comment,
        replies: [],
      },
      NICKNAMES,
    );

    expect(response.replies).toEqual([]);
  });
});

describe('authorsOf', () => {
  it('댓글과 답글을 쓴 사람들이다. 지운 것은 뺀다', () => {
    const reply = { ...COMMENT, id: '58', parentId: '57', authorId: REPLIER };
    const gone = {
      ...COMMENT,
      id: '59',
      parentId: '57',
      authorId: 'c4a1b2d3-5e6f-4a7b-8c9d-0e1f2a3b4c5d',
      deletedAt: new Date('2026-10-11T10:00:00.000Z'),
    };

    expect(
      authorsOf([
        {
          comment: COMMENT as Comment,
          replies: [reply as Comment, gone as Comment],
        },
      ]),
    ).toEqual([WRITER, REPLIER]);
  });
});
