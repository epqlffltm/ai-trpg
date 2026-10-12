// board-server/src/reports/report-dtos.spec.ts

/**
 * 신고할 때와 처리할 때 받는 값의 규칙(create-report.dto.ts, handle-reports.dto.ts)을 검증한다.
 * 서버를 띄우지 않고, 앱이 쓰는 것과 같은 파이프에 값을 넣어 본다.
 */

import { BadRequestException, Type } from '@nestjs/common';
import { validationPipe } from '../errors/validation.js';
import { CreateReportDto, descriptionProblem } from './create-report.dto.js';
import { HandleReportsDto } from './handle-reports.dto.js';
import { ListReportsQuery } from './list-reports.query.js';
import { DESCRIPTION_MAX_LENGTH } from './reports.policy.js';

/** 값을 DTO 의 규칙대로 검사한다. 통과하면 바뀐 값을 돌려준다. */
function check<Dto>(
  dto: Type<Dto>,
  value: unknown,
  type: 'body' | 'query' = 'body',
): Promise<Dto> {
  return validationPipe().transform(value, { type, metatype: dto });
}

/** 검사에 걸린 칸마다의 까닭. 통과하면 빈 객체다. */
async function rejected<Dto>(
  dto: Type<Dto>,
  value: unknown,
): Promise<Record<string, string[]>> {
  const failure = await check(dto, value).then(
    () => undefined,
    (error: unknown) => error,
  );
  if (failure === undefined) {
    return {};
  }
  expect(failure).toBeInstanceOf(BadRequestException);
  return (
    (failure as BadRequestException).getResponse() as {
      errors: Record<string, string[]>;
    }
  ).errors;
}

describe('CreateReportDto', () => {
  it.each([
    { reason: 'spam' },
    { reason: 'spam', description: null },
    { reason: 'abuse', description: '설명' },
    { reason: 'other', description: '설명' },
    { reason: 'other', description: 'a'.repeat(DESCRIPTION_MAX_LENGTH) },
  ])('받는다: %j', async (value) => {
    expect(await rejected(CreateReportDto, value)).toEqual({});
  });

  it('설명은 받은 그대로 둔다', async () => {
    const input = await check(CreateReportDto, {
      reason: 'spam',
      description: '  앞뒤 빈칸\n줄바꿈 ',
    });

    expect(input.description).toBe('  앞뒤 빈칸\n줄바꿈 ');
  });

  it('사유가 없거나 정해 둔 것이 아니면 거부한다', async () => {
    for (const value of [{}, { reason: 'boring' }, { reason: 1 }]) {
      expect(Object.keys(await rejected(CreateReportDto, value))).toEqual([
        'reason',
      ]);
    }
  });

  it('기타를 고르고 설명을 적지 않으면 그 까닭 하나만 알려 준다', async () => {
    for (const value of [
      { reason: 'other' },
      { reason: 'other', description: null },
    ]) {
      expect(await rejected(CreateReportDto, value)).toEqual({
        description: ['기타(other)를 고르면 설명을 적어야 합니다.'],
      });
    }
  });

  it('설명의 길이는 글과 댓글처럼 센다. 그림 글자 하나는 한 자다', async () => {
    const description = '😀'.repeat(DESCRIPTION_MAX_LENGTH);

    expect(
      await rejected(CreateReportDto, { reason: 'spam', description }),
    ).toEqual({});
  });

  it.each([
    ['빈칸만', '   '],
    ['빈 글자', ''],
    ['숫자', 3],
    ['NUL', 'a\u0000b'],
    ['너무 긴 것', 'a'.repeat(DESCRIPTION_MAX_LENGTH + 1)],
  ])('설명이 %s 이면 거부한다. 까닭은 하나다', async (_, description) => {
    const errors = await rejected(CreateReportDto, {
      reason: 'spam',
      description,
    });

    expect(Object.keys(errors)).toEqual(['description']);
    expect(errors.description).toHaveLength(1);
  });

  it('검사의 까닭에 받은 설명을 싣지 않는다', async () => {
    const description = `비밀스러운 설명 ${'a'.repeat(DESCRIPTION_MAX_LENGTH)}`;

    const errors = await rejected(CreateReportDto, {
      reason: 'spam',
      description,
    });

    expect(JSON.stringify(errors)).not.toContain('비밀스러운');
  });

  it('모르는 칸은 거부한다', async () => {
    const errors = await rejected(CreateReportDto, {
      reason: 'spam',
      reporter_id: 'someone',
    });

    expect(Object.keys(errors)).toEqual(['reporter_id']);
  });
});

describe('HandleReportsDto', () => {
  it.each(['actioned', 'dismissed'])('%s 를 받는다', async (outcome) => {
    expect(await rejected(HandleReportsDto, { outcome })).toEqual({});
  });

  it.each([{}, { outcome: 'deleted' }, { outcome: null }])(
    '거부한다: %j',
    async (value) => {
      expect(Object.keys(await rejected(HandleReportsDto, value))).toEqual([
        'outcome',
      ]);
    },
  );
});

describe('ListReportsQuery', () => {
  it('글 목록과 같은 쪽 규칙이다', async () => {
    const query = await check(ListReportsQuery, { page: '2' }, 'query');

    expect(query).toMatchObject({ page: 2, size: 20 });
  });
});

describe('descriptionProblem', () => {
  it.each([
    ['spam', undefined],
    ['spam', null],
    ['other', '설명'],
    ['spam', '설명'],
  ])('%s, %j 은 맞다', (reason, description) => {
    expect(descriptionProblem(reason, description)).toBeUndefined();
  });

  it.each([
    ['other', undefined, '기타(other)를 고르면 설명을 적어야 합니다.'],
    ['spam', 3, '설명은 글자여야 합니다.'],
    ['spam', ' \n', '설명을 적어야 합니다.'],
    ['spam', 'a\u0000', '설명에 쓸 수 없는 글자가 있습니다.'],
    [
      'spam',
      'a'.repeat(DESCRIPTION_MAX_LENGTH + 1),
      `설명은 ${DESCRIPTION_MAX_LENGTH}자를 넘을 수 없습니다.`,
    ],
  ])('%s, %j 은 틀렸다', (reason, description, problem) => {
    expect(descriptionProblem(reason, description)).toBe(problem);
  });
});
