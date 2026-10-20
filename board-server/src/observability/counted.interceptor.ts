// board-server/src/observability/counted.interceptor.ts

/**
 * 글과 댓글을 쓴 것(board_writes_total)과 신고한 것(board_reports_total)을 결과마다 세는 인터셉터.
 * 컨트롤러의 핸들러에 붙인다(@UseInterceptors(countWrite('post', 'create'))).
 *
 * 결과는 핸들러가 어떻게 끝났는지로 정한다. 셋이다.
 *   - success: 답을 돌려줬다. 저장(커밋)한 뒤다. 핸들러는 저장을 마치고 돌아온다
 *   - rate_limited: 쓰기 횟수 제한에 걸렸다(429)
 *   - rejected: 받지 않았다(400, 403, 404, 409). 모양이 틀렸거나, 남의 것이거나, 없는 것이거나, 이미 신고했다
 * 서버의 잘못(5xx)과 그 밖의 예외는 세지 않는다. 요청의 메트릭(http_server_requests_total 의 5xx)이 센다.
 * 로그인하지 않은 요청(401)은 가드에서 끝나 여기까지 오지 않는다. 쓰기가 아니다.
 * 본문의 모양을 보는 것(ValidationPipe)은 인터셉터 안에서 돈다. 그래서 모양이 틀린 쓰기도 rejected 로 센다.
 */

import {
  CallHandler,
  HttpException,
  HttpStatus,
  NestInterceptor,
} from '@nestjs/common';
import { Observable, tap } from 'rxjs';
import { recordReport, recordWrite, WriteResult } from './metrics.js';

/** 핸들러가 낸 예외의 결과. 세지 않는 것(서버의 잘못)이면 undefined 다. */
export function resultOfError(error: unknown): WriteResult | undefined {
  if (!(error instanceof HttpException)) {
    return undefined;
  }
  const status = error.getStatus();
  if (status === HttpStatus.TOO_MANY_REQUESTS) {
    return 'rate_limited';
  }
  return status < HttpStatus.INTERNAL_SERVER_ERROR ? 'rejected' : undefined;
}

/** 핸들러가 끝난 모양을 count 로 센다. 예외는 센 뒤에 그대로 올린다. */
export class Counted implements NestInterceptor {
  constructor(private readonly count: (result: WriteResult) => void) {}

  intercept(_context: unknown, next: CallHandler): Observable<unknown> {
    return next.handle().pipe(
      tap({
        complete: () => this.count('success'),
        error: (error: unknown) => {
          const result = resultOfError(error);
          if (result !== undefined) {
            this.count(result);
          }
        },
      }),
    );
  }
}

/** 글이나 댓글을 쓴 것을 센다. */
export function countWrite(
  resource: 'post' | 'comment',
  action: 'create' | 'update' | 'delete',
): Counted {
  return new Counted((result) => recordWrite(resource, action, result));
}

/** 글이나 댓글을 신고한 것을 센다. */
export function countReport(target: 'post' | 'comment'): Counted {
  return new Counted((result) => recordReport(target, result));
}
