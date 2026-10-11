// board-server/src/comments/comment-dtos.spec.ts

/**
 * 댓글을 쓰고 고치고 목록을 부를 때 받는 값의 규칙(create-comment.dto.ts, update-comment.dto.ts, list-comments.query.ts)을
 * 검증한다. 서버를 띄우지 않고, 앱이 쓰는 것과 같은 파이프에 값을 넣어 본다.
 */

import { ArgumentMetadata, BadRequestException, Type } from '@nestjs/common';
import { validationPipe } from '../errors/validation.js';
import { COMMENT_MAX_LENGTH } from './comment.entity.js';
import { CreateCommentDto } from './create-comment.dto.js';
import { ListCommentsQuery } from './list-comments.query.js';
import { DEFAULT_SLICE_SIZE, MAX_SLICE_SIZE } from './slice.js';
import { UpdateCommentDto } from './update-comment.dto.js';

/** 값을 DTO 의 규칙대로 검사한다. 통과하면 바뀐 값을 돌려준다. */
function check<Dto>(
  dto: Type<Dto>,
  value: unknown,
  type: ArgumentMetadata['type'] = 'body',
): Promise<Dto> {
  return validationPipe().transform(value, { type, metatype: dto });
}

/** 검사에 걸린 칸의 이름들. 통과하면 빈 목록이다. */
async function rejectedFields<Dto>(
  dto: Type<Dto>,
  value: unknown,
  type: ArgumentMetadata['type'] = 'body',
): Promise<string[]> {
  const failure = await check(dto, value, type).then(
    () => undefined,
    (error: unknown) => error,
  );
  if (failure === undefined) {
    return [];
  }
  expect(failure).toBeInstanceOf(BadRequestException);
  const body = (failure as BadRequestException).getResponse() as {
    errors: Record<string, string[]>;
  };
  return Object.keys(body.errors);
}

describe('CreateCommentDto', () => {
  it('내용만 있으면 글에 다는 댓글이다', async () => {
    const dto = await check(CreateCommentDto, { content: '댓글입니다.' });

    expect(dto).toEqual({ content: '댓글입니다.' });
  });

  it('어느 댓글에 다는지 적으면 답글이다', async () => {
    const dto = await check(CreateCommentDto, {
      content: '답글입니다.',
      parent_id: '57',
    });

    expect(dto.parent_id).toBe('57');
  });

  it('내용은 받은 그대로 둔다', async () => {
    const content = '  첫 줄\n둘째 줄  ';

    const dto = await check(CreateCommentDto, { content });

    expect(dto.content).toBe(content);
  });

  it('가장 긴 댓글을 받는다', async () => {
    const value = { content: '가'.repeat(COMMENT_MAX_LENGTH) };

    await expect(rejectedFields(CreateCommentDto, value)).resolves.toEqual([]);
  });

  it.each([
    ['없는 내용', {}],
    ['빈 내용', { content: '' }],
    ['빈칸과 줄바꿈뿐인 내용', { content: ' \n\t ' }],
    ['글자가 아닌 내용', { content: 42 }],
    ['너무 긴 내용', { content: '가'.repeat(COMMENT_MAX_LENGTH + 1) }],
    ['NUL 이 든 내용', { content: '댓\u0000글' }],
  ])('%s 은 거부한다', async (_name, value) => {
    await expect(rejectedFields(CreateCommentDto, value)).resolves.toEqual([
      'content',
    ]);
  });

  it.each([57, '0', '-1', 'abc', '1.5', '', '99999999999999999999', null])(
    '댓글 번호의 모양이 아닌 parent_id(%j)는 거부한다',
    async (parentId) => {
      const value = { content: '답글', parent_id: parentId };

      // null 은 적지 않은 것으로 본다. 그 밖에는 번호를 글자로 적어야 한다
      const expected = parentId === null ? [] : ['parent_id'];
      await expect(rejectedFields(CreateCommentDto, value)).resolves.toEqual(
        expected,
      );
    },
  );

  it('모르는 칸이 오면 거부한다', async () => {
    // 글쓴이는 토큰에서, 글은 주소에서 안다
    const value = { content: '댓글', author_id: 'x', post_id: '1' };

    await expect(rejectedFields(CreateCommentDto, value)).resolves.toEqual([
      'author_id',
      'post_id',
    ]);
  });
});

describe('UpdateCommentDto', () => {
  it('내용이 있으면 통과한다', async () => {
    await expect(
      check(UpdateCommentDto, { content: '고친 댓글' }),
    ).resolves.toEqual({ content: '고친 댓글' });
  });

  it.each([
    ['없는 내용', {}],
    ['빈칸뿐인 내용', { content: '   ' }],
    ['너무 긴 내용', { content: '가'.repeat(COMMENT_MAX_LENGTH + 1) }],
  ])('%s 은 거부한다', async (_name, value) => {
    await expect(rejectedFields(UpdateCommentDto, value)).resolves.toEqual([
      'content',
    ]);
  });

  it('다른 댓글의 답글로 옮길 수 없다', async () => {
    const value = { content: '고친 댓글', parent_id: '57' };

    await expect(rejectedFields(UpdateCommentDto, value)).resolves.toEqual([
      'parent_id',
    ]);
  });
});

describe('ListCommentsQuery', () => {
  it('적지 않으면 처음부터, 기본 크기다', async () => {
    const query = await check(ListCommentsQuery, {}, 'query');

    expect(query).toEqual({ size: DEFAULT_SLICE_SIZE });
  });

  it('after 는 글자 그대로, size 는 숫자로 읽는다', async () => {
    const query = await check(
      ListCommentsQuery,
      { after: '57', size: '10' },
      'query',
    );

    expect(query).toEqual({ after: '57', size: 10 });
  });

  it.each(['0', '-1', 'abc', '1.5', ''])(
    '댓글 번호의 모양이 아닌 after(%j)는 거부한다',
    async (after) => {
      await expect(
        rejectedFields(ListCommentsQuery, { after }, 'query'),
      ).resolves.toEqual(['after']);
    },
  );

  it.each(['0', '-5', 'all', String(MAX_SLICE_SIZE + 1)])(
    '크기가 될 수 없는 값(%j)은 거부한다',
    async (size) => {
      await expect(
        rejectedFields(ListCommentsQuery, { size }, 'query'),
      ).resolves.toEqual(['size']);
    },
  );
});
