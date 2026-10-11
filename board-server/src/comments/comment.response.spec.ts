// board-server/src/comments/comment.response.spec.ts

/**
 * 댓글을 응답의 모양으로 바꾸는 함수들(comment.response.ts)을 검증한다.
 */

import { Comment } from './comment.entity.js';
import {
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

describe('toCommentResponse', () => {
  it('댓글을 밑줄로 이은 칸 이름과 글자 번호로 내보낸다', () => {
    expect(toCommentResponse(COMMENT)).toEqual({
      id: '57',
      post_id: '1234',
      parent_id: null,
      author_id: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
      content: '댓글입니다.',
      deleted: false,
      created_at: '2026-10-11T09:00:00.000Z',
      updated_at: '2026-10-11T09:30:00.000Z',
    });
  });

  it('답글은 어느 댓글에 단 것인지 알린다', () => {
    const reply = { ...COMMENT, id: '58', parentId: '57' };

    expect(toCommentResponse(reply).parent_id).toBe('57');
  });

  it('지운 댓글은 누가 무엇을 썼는지 내보내지 않는다', () => {
    const deleted = {
      ...COMMENT,
      deletedAt: new Date('2026-10-11T10:00:00.000Z'),
    };

    expect(toCommentResponse(deleted)).toMatchObject({
      id: '57',
      author_id: null,
      content: null,
      deleted: true,
    });
  });
});

describe('toCommentThreadResponse', () => {
  it('댓글에 답글들을 붙여 내보낸다', () => {
    const reply = { ...COMMENT, id: '58', parentId: '57', content: '답글' };

    const response = toCommentThreadResponse({
      comment: COMMENT as Comment,
      replies: [reply as Comment],
    });

    expect(response).toMatchObject({ id: '57', content: '댓글입니다.' });
    expect(response.replies).toEqual([toCommentResponse(reply)]);
  });

  it('답글이 없으면 빈 목록이다', () => {
    const response = toCommentThreadResponse({
      comment: COMMENT as Comment,
      replies: [],
    });

    expect(response.replies).toEqual([]);
  });
});
