// board-server/src/errors/error-body.ts

/**
 * 오류 응답의 모양을 정한다. Nest 의 예외에서 응답의 본문을 만드는 순수한 함수들이다.
 *
 * 오류는 언제나 { "detail": "문장" } 이다. 인증 서버, 게임 서버, 결제 서버와 같은 칸 이름이다.
 * 입력이 틀렸을 때는 어느 칸이 왜 틀렸는지를 errors 에 더한다.
 *
 *     { "detail": "입력이 올바르지 않습니다.", "errors": { "title": ["제목을 적어야 합니다."] } }
 *
 * 너무 자주 불러서 거절할 때는 몇 초 뒤에 다시 부르면 되는지를 retry_after 에 더한다. 인증 서버와 같은 칸이다.
 *
 *     { "detail": "글을 너무 자주 쓰고 있습니다. 잠시 후 다시 시도해 주세요.", "retry_after": 142 }
 *
 * detail 은 이 서버가 적은 문장만 내보낸다. 예외를 던질 때 { detail } 을 넣은 것만 그대로 쓰고,
 * 나머지(Nest 나 라이브러리가 만든 예외)는 상태 코드에 맞는 문장으로 바꾼다.
 * 라이브러리의 글에는 내부 사정(주소, 파서의 오류)이 들어 있을 수 있다.
 */

import { HttpException, HttpStatus } from '@nestjs/common';

/** 칸의 이름마다 틀린 까닭들. */
export type FieldErrors = Record<string, string[]>;

/** 오류 응답의 본문. */
export interface ErrorBody {
  detail: string;
  errors?: FieldErrors;
  /** 몇 초 뒤에 다시 부르면 되는가. 1 이상의 정수다 */
  retry_after?: number;
}

/** 상태 코드마다의 기본 문장. 예외가 문장을 정해 주지 않았을 때 쓴다 */
const DEFAULT_DETAILS: Record<number, string> = {
  [HttpStatus.BAD_REQUEST]: '요청이 올바르지 않습니다.',
  [HttpStatus.UNAUTHORIZED]: '인증이 필요합니다.',
  [HttpStatus.FORBIDDEN]: '권한이 없습니다.',
  [HttpStatus.NOT_FOUND]: '찾을 수 없습니다.',
  [HttpStatus.METHOD_NOT_ALLOWED]: '허용되지 않는 요청입니다.',
  [HttpStatus.CONFLICT]: '요청이 지금 상태와 맞지 않습니다.',
  [HttpStatus.PAYLOAD_TOO_LARGE]: '요청이 너무 큽니다.',
  [HttpStatus.UNSUPPORTED_MEDIA_TYPE]: '지원하지 않는 형식입니다.',
  [HttpStatus.TOO_MANY_REQUESTS]: '요청이 너무 많습니다.',
  [HttpStatus.SERVICE_UNAVAILABLE]: '지금은 요청을 처리할 수 없습니다.',
};
/** 위에 없는 4xx 의 문장 */
const CLIENT_ERROR_DETAIL = '요청을 처리할 수 없습니다.';
/** 5xx 의 문장. 서버 안에서 무슨 일이 났는지 알리지 않는다 */
export const SERVER_ERROR_DETAIL = '서버에서 오류가 났습니다.';

/** 값이 이름과 값의 묶음(객체)인가. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** 값이 칸마다의 까닭들(글자 목록)인가. */
function isFieldErrors(value: unknown): value is FieldErrors {
  return (
    isRecord(value) &&
    Object.values(value).every(
      (messages) =>
        Array.isArray(messages) &&
        messages.every((message) => typeof message === 'string'),
    )
  );
}

/** 값이 기다릴 시간(초)으로 쓸 수 있는 수인가. 1 이상의 정수다. */
function isRetryAfter(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1;
}

/** 상태 코드에 맞는 기본 문장. */
export function defaultDetail(status: number): string {
  const known = DEFAULT_DETAILS[status];
  if (known !== undefined) {
    return known;
  }
  return status >= HttpStatus.INTERNAL_SERVER_ERROR
    ? SERVER_ERROR_DETAIL
    : CLIENT_ERROR_DETAIL;
}

/**
 * 예외에서 오류 응답의 본문을 만든다.
 *
 * 예외가 { detail } 을 담고 있으면 그 문장을 쓴다. 이 서버가 적은 문장이다.
 * 아니면 상태 코드의 기본 문장이다. errors 와 retry_after 는 모양이 맞을 때만 싣는다.
 */
export function errorBodyOf(exception: HttpException): ErrorBody {
  const response = exception.getResponse();
  if (!isRecord(response) || typeof response.detail !== 'string') {
    return { detail: defaultDetail(exception.getStatus()) };
  }
  return {
    detail: response.detail,
    ...(isFieldErrors(response.errors) && { errors: response.errors }),
    ...(isRetryAfter(response.retry_after) && {
      retry_after: response.retry_after,
    }),
  };
}
