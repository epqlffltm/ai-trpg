// board-server/src/auth/auth.module.ts

/**
 * 토큰 검증을 맡는 모듈. 회원가입과 로그인은 하지 않는다. 인증 서버가 발급한 토큰을 공개키로 검증만 한다.
 *
 *   - JWKS_LOADER: 인증 서버에서 키 목록을 가져오는 함수. 테스트가 가짜로 바꿔 꽂는다.
 *   - JwksCache: 가져온 키를 기억한다. 앱에 하나다.
 *   - TokenVerifier: 토큰을 검증한다.
 *   - APP_GUARD: 문지기(AuthGuard)를 앱 전체에 건다. 어느 모듈에 적든 모든 컨트롤러에 걸린다.
 *
 * 서버가 뜰 때는 인증 서버에 묻지 않는다. 첫 토큰이 올 때 키를 가져온다. 인증 서버가 꺼져 있어도 이 서버는 뜬다.
 */

import { Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { APP_GUARD } from '@nestjs/core';
import { Environment } from '../config/environment.js';
import { AuthGuard } from './auth.guard.js';
import { JwksCache, LoadKeys, loadKeys } from './jwks.js';
import { TokenVerifier } from './token-verifier.js';

/** 키 목록을 가져오는 함수를 꽂는 자리의 이름 */
export const JWKS_LOADER = Symbol('JWKS_LOADER');

/** 설정에 적힌 주소에서 키 목록을 가져오는 함수를 만든다. */
export function jwksLoader(config: ConfigService<Environment, true>): LoadKeys {
  const url = config.get('AUTH_JWKS_URL', { infer: true });
  return () => loadKeys(url);
}

@Module({
  providers: [
    { provide: JWKS_LOADER, inject: [ConfigService], useFactory: jwksLoader },
    {
      provide: JwksCache,
      inject: [JWKS_LOADER],
      useFactory: (load: LoadKeys) => new JwksCache(load),
    },
    TokenVerifier,
    { provide: APP_GUARD, useClass: AuthGuard },
  ],
})
export class AuthModule {}
