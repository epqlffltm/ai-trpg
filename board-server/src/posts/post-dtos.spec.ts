// board-server/src/posts/post-dtos.spec.ts

/**
 * 글을 쓰고 고치고 목록을 부를 때 받는 값의 규칙(create-post.dto.ts, update-post.dto.ts, list-posts.query.ts)을 검증한다.
 * 서버를 띄우지 않고, 앱이 쓰는 것과 같은 파이프에 값을 넣어 본다.
 */

import { ArgumentMetadata, BadRequestException, Type } from '@nestjs/common';
import { validationPipe } from '../errors/validation.js';
import { CreatePostDto } from './create-post.dto.js';
import { ListPostsQuery } from './list-posts.query.js';
import {
  DEFAULT_PAGE,
  DEFAULT_PAGE_SIZE,
  MAX_PAGE,
  MAX_PAGE_SIZE,
} from './page.js';
import { CONTENT_MAX_LENGTH, TITLE_MAX_LENGTH } from './post.entity.js';
import { UpdatePostDto } from './update-post.dto.js';

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

const VALID = { title: '첫 글', content: '본문입니다.' };

describe('CreatePostDto', () => {
  it('제목과 본문이 있으면 통과한다', async () => {
    await expect(check(CreatePostDto, VALID)).resolves.toEqual(VALID);
  });

  it('제목의 앞뒤 빈칸은 뗀다', async () => {
    const dto = await check(CreatePostDto, { ...VALID, title: '  첫 글  ' });

    expect(dto.title).toBe('첫 글');
  });

  it('본문은 받은 그대로 둔다', async () => {
    const content = '  들여쓴 첫 줄\n\n둘째 줄\n';

    const dto = await check(CreatePostDto, { ...VALID, content });

    expect(dto.content).toBe(content);
  });

  it('가장 긴 제목과 본문을 받는다', async () => {
    const value = {
      title: '가'.repeat(TITLE_MAX_LENGTH),
      content: '나'.repeat(CONTENT_MAX_LENGTH),
    };

    await expect(rejectedFields(CreatePostDto, value)).resolves.toEqual([]);
  });

  it.each([
    ['없는 제목', { content: '본문' }],
    ['빈 제목', { title: '', content: '본문' }],
    ['빈칸뿐인 제목', { title: '   ', content: '본문' }],
    ['글자가 아닌 제목', { title: 42, content: '본문' }],
    [
      '너무 긴 제목',
      { title: '가'.repeat(TITLE_MAX_LENGTH + 1), content: '본문' },
    ],
    ['NUL 이 든 제목', { title: '제\u0000목', content: '본문' }],
  ])('%s 은 거부한다', async (_name, value) => {
    await expect(rejectedFields(CreatePostDto, value)).resolves.toEqual([
      'title',
    ]);
  });

  it.each([
    ['없는 본문', { title: '제목' }],
    ['빈 본문', { title: '제목', content: '' }],
    ['빈칸과 줄바꿈뿐인 본문', { title: '제목', content: ' \n\t ' }],
    ['글자가 아닌 본문', { title: '제목', content: ['본문'] }],
    [
      '너무 긴 본문',
      { title: '제목', content: '나'.repeat(CONTENT_MAX_LENGTH + 1) },
    ],
    ['NUL 이 든 본문', { title: '제목', content: '본\u0000문' }],
  ])('%s 은 거부한다', async (_name, value) => {
    await expect(rejectedFields(CreatePostDto, value)).resolves.toEqual([
      'content',
    ]);
  });

  it('모르는 칸이 오면 거부한다', async () => {
    // 글쓴이는 토큰에서 안다. 본문으로 받지 않는다
    const value = {
      ...VALID,
      author_id: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
    };

    await expect(rejectedFields(CreatePostDto, value)).resolves.toEqual([
      'author_id',
    ]);
  });

  it('틀린 칸이 여럿이면 모두 알린다', async () => {
    await expect(rejectedFields(CreatePostDto, {})).resolves.toEqual([
      'title',
      'content',
    ]);
  });

  it('까닭은 우리말 문장이다', async () => {
    const failure = await check(CreatePostDto, { content: '본문' }).catch(
      (error: BadRequestException) => error.getResponse(),
    );

    expect(failure).toMatchObject({
      errors: { title: expect.arrayContaining(['제목을 적어야 합니다.']) },
    });
  });
});

describe('UpdatePostDto', () => {
  it('고칠 칸만 보내도 통과한다', async () => {
    await expect(check(UpdatePostDto, { title: '새 제목' })).resolves.toEqual({
      title: '새 제목',
    });
    await expect(check(UpdatePostDto, { content: '새 본문' })).resolves.toEqual(
      { content: '새 본문' },
    );
  });

  it('아무 칸도 보내지 않아도 모양은 맞다', async () => {
    // 고칠 내용이 없다는 것은 서비스가 거절한다(posts.service.ts)
    await expect(rejectedFields(UpdatePostDto, {})).resolves.toEqual([]);
  });

  it.each([
    ['빈 제목', { title: '  ' }, 'title'],
    ['너무 긴 제목', { title: '가'.repeat(TITLE_MAX_LENGTH + 1) }, 'title'],
    ['빈 본문', { content: '' }, 'content'],
    ['글자가 아닌 본문', { content: 42 }, 'content'],
  ])(
    '보낸 칸은 쓸 때와 같은 규칙으로 본다: %s',
    async (_name, value, field) => {
      await expect(rejectedFields(UpdatePostDto, value)).resolves.toEqual([
        field,
      ]);
    },
  );

  it('모르는 칸이 오면 거부한다', async () => {
    await expect(
      rejectedFields(UpdatePostDto, { board: 'notice' }),
    ).resolves.toEqual(['board']);
  });
});

describe('ListPostsQuery', () => {
  it('적지 않으면 첫 쪽, 기본 크기다', async () => {
    const query = await check(ListPostsQuery, {}, 'query');

    expect(query).toEqual({ page: DEFAULT_PAGE, size: DEFAULT_PAGE_SIZE });
  });

  it('주소의 글자를 숫자로 바꾼다', async () => {
    const query = await check(
      ListPostsQuery,
      { page: '3', size: '10' },
      'query',
    );

    expect(query).toEqual({ page: 3, size: 10 });
  });

  it('가장 뒤의 쪽과 가장 큰 크기를 받는다', async () => {
    const value = { page: String(MAX_PAGE), size: String(MAX_PAGE_SIZE) };

    await expect(
      rejectedFields(ListPostsQuery, value, 'query'),
    ).resolves.toEqual([]);
  });

  it.each(['0', '-1', '1.5', 'abc', '', String(MAX_PAGE + 1)])(
    '쪽이 될 수 없는 값(%j)은 거부한다',
    async (page) => {
      await expect(
        rejectedFields(ListPostsQuery, { page }, 'query'),
      ).resolves.toEqual(['page']);
    },
  );

  it.each(['0', '-5', '2.5', 'all', String(MAX_PAGE_SIZE + 1), '100000'])(
    '크기가 될 수 없는 값(%j)은 거부한다',
    async (size) => {
      await expect(
        rejectedFields(ListPostsQuery, { size }, 'query'),
      ).resolves.toEqual(['size']);
    },
  );
});
