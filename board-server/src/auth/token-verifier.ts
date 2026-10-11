// board-server/src/auth/token-verifier.ts

/**
 * 토큰을 검증하는 서비스. 검증의 규칙(tokens.ts)에 이 앱의 설정과 키 저장소를 물려 준다.
 *
 * 규칙 자체는 여기에 없다. 순수한 함수(verifyAccessToken)를 부르기만 한다.
 */

import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Environment } from '../config/environment.js';
import { JwksCache } from './jwks.js';
import { AccessClaims, TokenSettings, verifyAccessToken } from './tokens.js';

@Injectable()
export class TokenVerifier {
  private readonly settings: TokenSettings;

  constructor(
    private readonly jwks: JwksCache,
    config: ConfigService<Environment, true>,
  ) {
    this.settings = {
      JWT_ISSUER: config.get('JWT_ISSUER', { infer: true }),
      JWT_AUDIENCE: config.get('JWT_AUDIENCE', { infer: true }),
    };
  }

  /**
   * access 토큰을 검증하고 그 안의 값을 돌려준다.
   *
   * 토큰이 틀렸으면 InvalidTokenError, 키를 구할 수 없으면 JwksUnavailableError 다.
   */
  verify(token: string): Promise<AccessClaims> {
    return verifyAccessToken(token, this.jwks, this.settings);
  }
}
