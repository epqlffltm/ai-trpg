// board-server/src/authors/authors.interceptor.ts

/**
 * 로그인한 요청마다 토큰에 실려 온 닉네임을 적어 둔다. 앱 전체에 건다(authors.module.ts 의 APP_INTERCEPTOR).
 *
 * 문지기(auth/auth.guard.ts)가 토큰을 검증하고 요청에 주인을 적어 둔 뒤에 돈다. 컨트롤러보다는 먼저다.
 * 그래서 글을 쓴 응답에 바로 그 이름이 실린다.
 *
 * 글을 쓸 때만이 아니라 로그인한 요청이면 무엇이든 받는다. 이름을 바꾸고 게시판에 들어오기만 해도
 * (화면이 보통 처음에 부르는 GET /me 같은 것) 예전 글에 새 이름이 나온다.
 * 로그인 없이 부르는 주소(@Public, 글 목록과 읽기)는 토큰을 보지 않으므로 여기서도 받지 않는다.
 *
 * 문지기에 넣지 않았다. 문지기는 들여보낼지만 정한다. 이름을 적는 일은 다른 일이다.
 */

import {
  CallHandler,
  ExecutionContext,
  Injectable,
  NestInterceptor,
} from '@nestjs/common';
import { Observable } from 'rxjs';
import { AuthenticatedRequest } from '../auth/current-user.decorator.js';
import { AuthorsService } from './authors.service.js';

@Injectable()
export class AuthorsInterceptor implements NestInterceptor {
  constructor(private readonly authors: AuthorsService) {}

  async intercept(
    context: ExecutionContext,
    next: CallHandler,
  ): Promise<Observable<unknown>> {
    const user = context.switchToHttp().getRequest<AuthenticatedRequest>().user;
    if (user?.nickname !== undefined) {
      await this.authors.remember(user.userId, user.nickname);
    }
    return next.handle();
  }
}
