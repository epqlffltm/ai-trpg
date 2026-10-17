// board-server/src/auth/token-verifier.ts

/**
 * 토큰을 검증하는 서비스. 검증의 규칙(tokens.ts)에 이 앱의 설정과 키 저장소를 물려 준다.
 *
 * 규칙 자체는 여기에 없다. 순수한 함수(verifyAccessToken)를 부르기만 한다.
 * 검증을 통과한 토큰이 끊긴 세션의 것이면(session-revocations.ts) 받아들일 수 없는 토큰으로 본다(#274).
 */

import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Environment } from '../config/environment.js';
import { JwksCache } from './jwks.js';
import { RevocationCache } from './session-revocations.js';
import {
  AccessClaims,
  InvalidTokenError,
  TokenSettings,
  verifyAccessToken,
} from './tokens.js';

@Injectable()
export class TokenVerifier {
  private readonly settings: TokenSettings;

  constructor(
    private readonly jwks: JwksCache,
    private readonly revocations: RevocationCache,
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
   * 토큰이 틀렸거나 끊긴 세션의 것이면 InvalidTokenError, 키를 구할 수 없으면 JwksUnavailableError 다.
   * 끊긴 세션인지는 마지막으로 받은 목록으로 본다. 인증 서버에 묻지 않는다.
   */
  async verify(token: string): Promise<AccessClaims> {
    const claims = await verifyAccessToken(token, this.jwks, this.settings);
    if (this.revocations.revoked(claims.userId, claims.version)) {
      throw new InvalidTokenError();
    }
    return claims;
  }
}
