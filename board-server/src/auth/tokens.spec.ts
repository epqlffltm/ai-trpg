// board-server/src/auth/tokens.spec.ts

/**
 * 토큰을 검증하는 규칙(tokens.ts)을 검증한다. 인증 서버를 띄우지 않고, 테스트가 만든 키로 서명한다.
 * 맞는 토큰에서 한 가지씩만 틀리게 바꿔, 그 하나 때문에 거부되는지 본다.
 */

import { Logger } from '@nestjs/common';
import { SignJWT } from 'jose';
import {
  AUDIENCE,
  forgeToken,
  ISSUER,
  makeSigningKey,
  publicKeys,
  SigningKey,
  signToken,
  USER_ID,
  validClaims,
} from '../../test/tokens.js';
import { JwksCache, JwksFetchError, JwksUnavailableError } from './jwks.js';
import {
  buildAccessClaims,
  CLOCK_SKEW_SECONDS,
  InvalidTokenError,
  readKeyId,
  verifyAccessToken,
} from './tokens.js';

const SETTINGS = { JWT_ISSUER: ISSUER, JWT_AUDIENCE: AUDIENCE };

let key: SigningKey;
let stranger: SigningKey;
let jwks: JwksCache;

beforeAll(async () => {
  key = await makeSigningKey('key-1');
  // 인증 서버의 것이 아닌 키. kid 만 같다
  stranger = await makeSigningKey('key-1');
});

beforeEach(() => {
  jwks = new JwksCache(() => publicKeys(key));
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** 토큰을 검증해 본다. */
function verify(token: string) {
  return verifyAccessToken(token, jwks, SETTINGS);
}

describe('readKeyId', () => {
  it('머리말의 kid 를 읽는다', async () => {
    expect(readKeyId(await signToken(key))).toBe('key-1');
  });

  it.each(['', 'abc', 'a.b', 'a.b.c', '....'])(
    '토큰의 모양이 아니면(%j) 거부한다',
    (token) => {
      expect(() => readKeyId(token)).toThrow(InvalidTokenError);
    },
  );

  it.each(['none', 'HS256', 'RS512', 'ES256', undefined])(
    '서명 방식이 RS256 이 아니면(%j) 거부한다',
    (alg) => {
      const token = forgeToken({ alg, kid: 'key-1' }, validClaims());

      expect(() => readKeyId(token)).toThrow(InvalidTokenError);
    },
  );

  it.each([undefined, '', 42, null])('kid 가 없으면(%j) 거부한다', (kid) => {
    const token = forgeToken({ alg: 'RS256', kid }, validClaims());

    expect(() => readKeyId(token)).toThrow(InvalidTokenError);
  });
});

describe('buildAccessClaims', () => {
  it('주인의 ID 와 만료 시각을 꺼낸다', () => {
    const claims = buildAccessClaims({
      token_type: 'access',
      sub: USER_ID,
      exp: 1_800_000_000,
    });

    expect(claims).toEqual({
      userId: USER_ID,
      expiresAt: new Date('2027-01-15T08:00:00.000Z'),
      version: 0,
    });
  });

  it('세션 버전(ver)을 꺼낸다. 없으면 0 이다', () => {
    const claims = (ver?: unknown) =>
      buildAccessClaims({
        token_type: 'access',
        sub: USER_ID,
        exp: 1_800_000_000,
        ...(ver === undefined ? {} : { ver }),
      });

    expect(claims(3).version).toBe(3);
    expect(claims(0).version).toBe(0);
    expect(claims().version).toBe(0);
  });

  it.each([-1, 1.5, '3', null, true])(
    '세션 버전이 0 이상의 정수가 아니면 거부한다: %s',
    (ver) => {
      expect(() =>
        buildAccessClaims({
          token_type: 'access',
          sub: USER_ID,
          exp: 1_800_000_000,
          ver,
        }),
      ).toThrow(InvalidTokenError);
    },
  );

  it('닉네임이 있으면 함께 꺼낸다', () => {
    const claims = buildAccessClaims({
      token_type: 'access',
      sub: USER_ID,
      exp: 1_800_000_000,
      nickname: '모험가_01',
    });

    expect(claims.nickname).toBe('모험가_01');
  });

  it.each([undefined, '', 'a\u0000b', 3, 'x'.repeat(51)])(
    '닉네임을 받아들일 수 없어도(%j) 토큰은 받고 닉네임만 뺀다',
    (nickname) => {
      const claims = buildAccessClaims({
        token_type: 'access',
        sub: USER_ID,
        exp: 1_800_000_000,
        nickname,
      });

      expect(claims.userId).toBe(USER_ID);
      expect('nickname' in claims).toBe(false);
    },
  );

  it('ID 는 소문자로 맞춘다', () => {
    const claims = buildAccessClaims({
      token_type: 'access',
      sub: USER_ID.toUpperCase(),
      exp: 1_800_000_000,
    });

    // 같은 사람이 대소문자만 다른 두 ID 로 저장되지 않게 한다
    expect(claims.userId).toBe(USER_ID);
  });

  it.each(['refresh', 'ACCESS', '', undefined, 1])(
    'access 토큰이 아니면(%j) 거부한다',
    (tokenType) => {
      expect(() =>
        buildAccessClaims({ token_type: tokenType, sub: USER_ID, exp: 1 }),
      ).toThrow(InvalidTokenError);
    },
  );

  it.each([undefined, '', '42', 'not-a-uuid', `${USER_ID}x`, ` ${USER_ID}`])(
    '주인의 ID 가 UUID 가 아니면(%j) 거부한다',
    (sub) => {
      expect(() =>
        buildAccessClaims({ token_type: 'access', sub, exp: 1 }),
      ).toThrow(InvalidTokenError);
    },
  );
});

describe('verifyAccessToken', () => {
  it('인증 서버가 발급한 access 토큰을 받아들인다', async () => {
    const claims = await verify(await signToken(key));

    expect(claims.userId).toBe(USER_ID);
    expect(claims.expiresAt.getTime()).toBeGreaterThan(Date.now());
  });

  it('대상이 목록이 아니라 이 서버의 이름 하나여도 받아들인다', async () => {
    const token = await signToken(key, { audience: AUDIENCE });

    await expect(verify(token)).resolves.toBeDefined();
  });

  it('만료된 토큰은 거부한다', async () => {
    const token = await signToken(key, {
      expiresInSeconds: -CLOCK_SKEW_SECONDS - 5,
    });

    await expect(verify(token)).rejects.toThrow(InvalidTokenError);
  });

  it('시계가 조금 어긋난 만큼은 봐준다', async () => {
    const token = await signToken(key, { expiresInSeconds: -3 });

    await expect(verify(token)).resolves.toBeDefined();
  });

  it('다른 서버에만 쓰라고 발급된 토큰은 거부한다', async () => {
    // 인증 서버의 JWT_AUDIENCE 에 게시판 서버의 이름이 없을 때의 토큰
    const token = await signToken(key, {
      audience: ['ai-trpg-auth', 'ai-trpg-game'],
    });

    await expect(verify(token)).rejects.toThrow(InvalidTokenError);
  });

  it('다른 곳이 발급한 토큰은 거부한다', async () => {
    const token = await signToken(key, { issuer: 'someone-else' });

    await expect(verify(token)).rejects.toThrow(InvalidTokenError);
  });

  it('refresh 토큰은 거부한다', async () => {
    const token = await signToken(key, { tokenType: 'refresh' });

    await expect(verify(token)).rejects.toThrow(InvalidTokenError);
  });

  it('주인의 ID 가 UUID 가 아니면 거부한다', async () => {
    const token = await signToken(key, { subject: '42' });

    await expect(verify(token)).rejects.toThrow(InvalidTokenError);
  });

  it('kid 만 같은 다른 키로 서명한 토큰은 거부한다', async () => {
    const token = await signToken(stranger);

    await expect(verify(token)).rejects.toThrow(InvalidTokenError);
  });

  it('모르는 kid 의 토큰은 거부한다', async () => {
    const token = await signToken(key, { kid: 'forged' });

    await expect(verify(token)).rejects.toThrow(InvalidTokenError);
  });

  it('내용을 고친 토큰은 거부한다', async () => {
    const [header, , signature] = (await signToken(key)).split('.');
    const someoneElse = { ...validClaims(), sub: USER_ID.replace('0', '1') };
    // 머리말과 서명은 그대로 두고 내용만 남의 ID 로 바꿔 끼운다
    const [, claims] = forgeToken({}, someoneElse).split('.');

    await expect(verify(`${header}.${claims}.${signature}`)).rejects.toThrow(
      InvalidTokenError,
    );
  });

  it('서명이 없는 토큰(none)은 거부한다', async () => {
    const token = forgeToken({ alg: 'none', kid: 'key-1' }, validClaims());

    await expect(verify(token)).rejects.toThrow(InvalidTokenError);
  });

  it('공개키를 비밀키처럼 써서 만든 토큰(HS256)은 거부한다', async () => {
    const secret = new TextEncoder().encode(JSON.stringify(key.jwk));
    const token = await new SignJWT(validClaims())
      .setProtectedHeader({ alg: 'HS256', kid: 'key-1' })
      .sign(secret);

    await expect(verify(token)).rejects.toThrow(InvalidTokenError);
  });

  it.each(['exp', 'iss', 'aud', 'sub'])(
    '%s 가 없는 토큰은 거부한다',
    async (claim) => {
      const claims = validClaims();
      delete claims[claim];
      const token = await new SignJWT(claims)
        .setProtectedHeader({ alg: 'RS256', kid: 'key-1' })
        .sign(key.privateKey);

      await expect(verify(token)).rejects.toThrow(InvalidTokenError);
    },
  );

  it('키를 구할 수 없으면 틀린 토큰이 아니라 확인할 수 없는 것이다', async () => {
    const down = new JwksCache(() =>
      Promise.reject(new JwksFetchError('TypeError')),
    );
    vi.spyOn(Logger.prototype, 'warn').mockImplementation(() => undefined);

    await expect(
      verifyAccessToken(await signToken(key), down, SETTINGS),
    ).rejects.toThrow(JwksUnavailableError);
  });

  it('틀린 토큰이라는 것만 알리고 까닭은 싣지 않는다', async () => {
    const token = await signToken(key, { expiresInSeconds: -60 });

    const failure = await verify(token).catch((error: unknown) => error);

    expect((failure as Error).message).toBe('');
  });
});
