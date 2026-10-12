// board-server/src/errors/all-exceptions.filter.spec.ts

/**
 * 예외를 응답으로 바꾸는 필터(all-exceptions.filter.ts)를 검증한다. 서버를 띄우지 않는다.
 * 앱에 실제로 걸려 있는지는 test/errors.e2e-spec.ts 가 본다.
 */

import {
  ArgumentsHost,
  ForbiddenException,
  Logger,
  HttpException,
  NotFoundException,
} from '@nestjs/common';
import { AllExceptionsFilter } from './all-exceptions.filter.js';

/** 필터에 넘길 가짜 응답. 정해진 상태 코드와 본문, 붙은 머리말을 기억한다. */
function makeHost() {
  const sent: {
    status?: number;
    body?: unknown;
    headers?: Record<string, string>;
  } = {};
  const response = {
    setHeader: (name: string, value: string) => {
      sent.headers = { ...sent.headers, [name]: value };
    },
    status: (code: number) => {
      sent.status = code;
      return { json: (body: unknown) => (sent.body = body) };
    },
  };
  const host = {
    switchToHttp: () => ({ getResponse: () => response }),
  } as unknown as ArgumentsHost;
  return { sent, host };
}

describe('AllExceptionsFilter', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('HTTP 예외는 그 상태 코드와 문장으로 답한다', () => {
    const { sent, host } = makeHost();

    new AllExceptionsFilter().catch(
      new ForbiddenException({ detail: '자신의 글만 고칠 수 있습니다.' }),
      host,
    );

    expect(sent).toEqual({
      status: 403,
      body: { detail: '자신의 글만 고칠 수 있습니다.' },
    });
  });

  it('기다릴 시간이 있으면 본문과 Retry-After 머리말에 함께 싣는다', () => {
    const { sent, host } = makeHost();

    new AllExceptionsFilter().catch(
      new HttpException({ detail: '너무 자주 씁니다.', retry_after: 142 }, 429),
      host,
    );

    expect(sent).toEqual({
      status: 429,
      body: { detail: '너무 자주 씁니다.', retry_after: 142 },
      headers: { 'Retry-After': '142' },
    });
  });

  it('기다릴 시간이 없으면 Retry-After 를 붙이지 않는다', () => {
    const { sent, host } = makeHost();

    new AllExceptionsFilter().catch(
      new ForbiddenException({ detail: '권한이 없습니다.' }),
      host,
    );

    expect(sent.headers).toBeUndefined();
  });

  it('Nest 가 만든 예외의 글은 내보내지 않는다', () => {
    const { sent, host } = makeHost();

    new AllExceptionsFilter().catch(
      new NotFoundException('Cannot GET /nope'),
      host,
    );

    expect(sent).toEqual({
      status: 404,
      body: { detail: '찾을 수 없습니다.' },
    });
  });

  it('뜻밖의 예외는 500 이고, 예외의 글을 내보내지 않는다', () => {
    vi.spyOn(Logger.prototype, 'error').mockImplementation(() => undefined);
    const { sent, host } = makeHost();
    // DB 드라이버가 내는 오류의 흉내. 쿼리와 계정 이름이 들어 있다
    const failure = new Error('relation "board.posts" does not exist');

    new AllExceptionsFilter().catch(failure, host);

    expect(sent).toEqual({
      status: 500,
      body: { detail: '서버에서 오류가 났습니다.' },
    });
  });

  it('뜻밖의 예외는 어디서 났는지까지 공통 규격의 칸으로 로그에 남긴다', () => {
    const error = vi
      .spyOn(Logger.prototype, 'error')
      .mockImplementation(() => undefined);
    const failure = new RangeError('버그');

    new AllExceptionsFilter().catch(failure, makeHost().host);

    expect(error).toHaveBeenCalledWith(
      {
        message: '버그',
        operation: 'http.request',
        error_code: 'http.unhandled_exception',
        error_type: 'RangeError',
      },
      failure.stack,
    );
  });

  it('예외가 아닌 값이 던져져도 500 으로 답한다', () => {
    vi.spyOn(Logger.prototype, 'error').mockImplementation(() => undefined);
    const { sent, host } = makeHost();

    new AllExceptionsFilter().catch('글자를 던졌다', host);

    expect(sent.status).toBe(500);
  });
});
