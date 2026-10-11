// board-server/src/auth/public.decorator.ts

/**
 * 로그인 없이 부를 수 있는 API 라는 표시.
 *
 * 이 서버의 API 는 기본으로 로그인이 필요하다(auth.guard.ts). 열어 둘 API 에만 이 표시를 붙인다.
 * 표시를 빠뜨린 API 가 열려 있는 것보다 닫혀 있는 쪽이 안전하다. 인증 서버의 기본(IsAuthenticated)과 같은 생각이다.
 *
 *     @Public()
 *     @Get()
 *     list() { ... }
 *
 * 컨트롤러에 붙이면 그 안의 API 가 모두 열린다.
 */

import { SetMetadata } from '@nestjs/common';

/** 표시를 적어 두는 이름. 문지기(AuthGuard)가 이 이름으로 읽는다 */
export const IS_PUBLIC = 'isPublic';

/** 로그인 없이 부를 수 있다고 표시한다. */
export const Public = () => SetMetadata(IS_PUBLIC, true);
