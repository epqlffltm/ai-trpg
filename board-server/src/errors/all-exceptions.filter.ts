// board-server/src/errors/all-exceptions.filter.ts

/**
 * 컨트롤러와 문지기에서 올라온 예외를 응답으로 바꾼다. 앱 전체에 건다(app.module.ts 의 APP_FILTER).
 *
 *   - Nest 의 HTTP 예외: 그 상태 코드로, 본문은 { detail } 모양으로 맞춰 보낸다(error-body.ts).
 *   - 그 밖의 예외: 코드를 잘못 짰거나 DB 가 실패한 것이다. 500 으로 답하고 로그에 남긴다.
 *     예외의 글은 응답에 싣지 않는다. 쿼리와 DB 주소가 들어 있을 수 있다.
 *
 * 응답에 이미 붙은 머리말은 그대로 나간다. 문지기가 붙인 WWW-Authenticate 와 Retry-After 가 그렇다.
 */

import {
  ArgumentsHost,
  Catch,
  ExceptionFilter,
  HttpException,
  HttpStatus,
  Logger,
} from '@nestjs/common';
import { HTTP_OPERATION } from '../observability/request-logging.middleware.js';
import { ErrorBody, errorBodyOf, SERVER_ERROR_DETAIL } from './error-body.js';

/** 이 필터가 쓰는 응답의 부분. */
interface OutgoingResponse {
  status(code: number): { json(body: ErrorBody): unknown };
}

@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
  private readonly logger = new Logger(AllExceptionsFilter.name);

  catch(exception: unknown, host: ArgumentsHost): void {
    const response = host.switchToHttp().getResponse<OutgoingResponse>();
    if (exception instanceof HttpException) {
      response.status(exception.getStatus()).json(errorBodyOf(exception));
      return;
    }
    this.logUnexpected(exception);
    response
      .status(HttpStatus.INTERNAL_SERVER_ERROR)
      .json({ detail: SERVER_ERROR_DETAIL });
  }

  /**
   * 뜻밖의 예외를 로그에 남긴다. 어디서 났는지(stack)까지 남긴다. 로그는 서버 안에서만 본다.
   *
   * 공통 규격의 칸으로 남긴다(저장소 루트의 docs/observability.md). 요청의 식별자는 로거가 붙인다.
   */
  private logUnexpected(exception: unknown): void {
    if (exception instanceof Error) {
      this.logger.error(unhandledFields(exception), exception.stack);
      return;
    }
    this.logger.error({
      message: `예외가 아닌 값이 올라왔다: ${typeof exception}`,
      operation: HTTP_OPERATION,
      error_code: UNHANDLED_ERROR_CODE,
    });
  }
}

/** 처리하지 못한 예외의 오류 코드 */
export const UNHANDLED_ERROR_CODE = 'http.unhandled_exception';

/** 처리하지 못한 예외를 남기는 줄에 싣는 칸들. 예외의 기록은 따로 넘긴다. */
export function unhandledFields(exception: Error): Record<string, string> {
  return {
    message: exception.message,
    operation: HTTP_OPERATION,
    error_code: UNHANDLED_ERROR_CODE,
    error_type: exception.constructor.name,
  };
}
