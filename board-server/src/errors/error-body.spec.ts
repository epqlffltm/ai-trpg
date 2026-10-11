// board-server/src/errors/error-body.spec.ts

/**
 * 예외에서 오류 응답의 본문을 만드는 함수들(error-body.ts)을 검증한다.
 */

import {
  BadRequestException,
  HttpException,
  NotFoundException,
} from '@nestjs/common';
import {
  defaultDetail,
  errorBodyOf,
  SERVER_ERROR_DETAIL,
} from './error-body.js';

describe('defaultDetail', () => {
  it.each([
    [400, '요청이 올바르지 않습니다.'],
    [401, '인증이 필요합니다.'],
    [403, '권한이 없습니다.'],
    [404, '찾을 수 없습니다.'],
    [503, '지금은 요청을 처리할 수 없습니다.'],
  ])('%i 의 문장이 정해져 있다', (status, detail) => {
    expect(defaultDetail(status)).toBe(detail);
  });

  it('정해 두지 않은 4xx 는 요청을 처리할 수 없다고 한다', () => {
    expect(defaultDetail(418)).toBe('요청을 처리할 수 없습니다.');
  });

  it.each([500, 502, 599])('5xx(%i) 는 서버의 오류라고만 한다', (status) => {
    expect(defaultDetail(status)).toBe(SERVER_ERROR_DETAIL);
  });
});

describe('errorBodyOf', () => {
  it('예외가 담은 문장을 그대로 쓴다', () => {
    const exception = new NotFoundException({
      detail: '글을 찾을 수 없습니다.',
    });

    expect(errorBodyOf(exception)).toEqual({
      detail: '글을 찾을 수 없습니다.',
    });
  });

  it('칸마다의 까닭이 있으면 함께 싣는다', () => {
    const exception = new BadRequestException({
      detail: '입력이 올바르지 않습니다.',
      errors: { title: ['제목을 적어야 합니다.'] },
    });

    expect(errorBodyOf(exception)).toEqual({
      detail: '입력이 올바르지 않습니다.',
      errors: { title: ['제목을 적어야 합니다.'] },
    });
  });

  it('Nest 가 만든 예외의 글은 내보내지 않는다', () => {
    // 없는 주소를 부르면 Nest 가 이런 글로 예외를 만든다
    const exception = new NotFoundException('Cannot GET /api/v1/board/nope');

    expect(errorBodyOf(exception)).toEqual({ detail: '찾을 수 없습니다.' });
  });

  it('라이브러리가 만든 예외의 글은 내보내지 않는다', () => {
    // 본문의 JSON 이 깨졌을 때 파서가 내는 글
    const exception = new BadRequestException(
      'Unexpected token } in JSON at position 12',
    );

    expect(errorBodyOf(exception)).toEqual({
      detail: '요청이 올바르지 않습니다.',
    });
  });

  it('문장 없이 던진 예외는 상태 코드의 문장을 쓴다', () => {
    expect(errorBodyOf(new HttpException('글', 409))).toEqual({
      detail: '요청이 지금 상태와 맞지 않습니다.',
    });
  });

  it.each([42, null, ['글']])(
    'detail 이 글자가 아니면(%j) 상태 코드의 문장을 쓴다',
    (detail) => {
      const exception = new BadRequestException({ detail });

      expect(errorBodyOf(exception)).toEqual({
        detail: '요청이 올바르지 않습니다.',
      });
    },
  );

  it.each([
    '글',
    ['제목'],
    { title: '제목을 적어야 합니다.' },
    { title: [42] },
  ])('errors 의 모양이 틀리면(%j) 싣지 않는다', (errors) => {
    const exception = new BadRequestException({ detail: '문장', errors });

    expect(errorBodyOf(exception)).toEqual({ detail: '문장' });
  });

  it('detail 과 errors 밖의 칸은 내보내지 않는다', () => {
    const exception = new BadRequestException({
      detail: '문장',
      query: 'SELECT * FROM posts',
    });

    expect(errorBodyOf(exception)).toEqual({ detail: '문장' });
  });
});
