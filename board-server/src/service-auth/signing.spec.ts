// board-server/src/service-auth/signing.spec.ts

import {
  isValidSignature,
  MIN_SECRET_LENGTH,
  sign,
  TOLERANCE_SECONDS,
} from './signing.js';

const SECRET = 'x'.repeat(40);
const PATH =
  '/api/v1/board/service/users/6f1e2d3c-4b5a-4c6d-8e7f-0a1b2c3d4e5f/withdrawal';
const BODY = '{"withdrawn_at":"2026-10-28T03:00:00+00:00"}';
const NOW = 1_793_156_400;

/** 이 요청을 받아들이는가. 바꿔 볼 것만 넘긴다. */
function accepts(
  header: string | undefined,
  overrides: Partial<{
    secret: string;
    method: string;
    path: string;
    body: string;
    now: number;
  }> = {},
): boolean {
  return isValidSignature(
    overrides.secret ?? SECRET,
    header,
    overrides.method ?? 'POST',
    overrides.path ?? PATH,
    Buffer.from(overrides.body ?? BODY, 'utf8'),
    overrides.now ?? NOW,
  );
}

describe('isValidSignature', () => {
  it('같은 비밀로 그 요청에 한 서명을 받는다', () => {
    expect(accepts(sign(SECRET, NOW, 'POST', PATH, BODY))).toBe(true);
  });

  it('파이썬의 hmac 으로 만든 서명을 받는다. 인증 서버와 같은 모양이다', () => {
    // python3: hmac.new(secret, b"<시각>.POST\n<경로>\n" + body, sha256).hexdigest()
    const header =
      't=1793156400,v1=474f425581b4385c441f17cd46ba37d0729b254f888587257b1415da1a644ce1';
    expect(accepts(header)).toBe(true);
  });

  it.each([
    ['다른 비밀', { secret: 'y'.repeat(40) }],
    ['다른 메서드', { method: 'PUT' }],
    ['다른 경로', { path: PATH.replace('6f1e', '7f1e') }],
    ['바뀐 본문', { body: BODY.replace('28', '29') }],
  ])('%s 의 요청이면 받지 않는다', (_, overrides) => {
    expect(accepts(sign(SECRET, NOW, 'POST', PATH, BODY), overrides)).toBe(
      false,
    );
  });

  it(`시각이 ${TOLERANCE_SECONDS}초를 넘게 어긋나면 받지 않는다`, () => {
    const header = sign(SECRET, NOW, 'POST', PATH, BODY);
    expect(accepts(header, { now: NOW + TOLERANCE_SECONDS })).toBe(true);
    expect(accepts(header, { now: NOW + TOLERANCE_SECONDS + 1 })).toBe(false);
    expect(accepts(header, { now: NOW - TOLERANCE_SECONDS - 1 })).toBe(false);
  });

  it('비밀이 비었거나 짧으면 그 비밀로 한 서명도 받지 않는다', () => {
    const short = 'z'.repeat(MIN_SECRET_LENGTH - 1);
    expect(
      accepts(sign(short, NOW, 'POST', PATH, BODY), { secret: short }),
    ).toBe(false);
    expect(accepts(sign('', NOW, 'POST', PATH, BODY), { secret: '' })).toBe(
      false,
    );
  });

  it.each([
    undefined,
    '',
    't=1793156400',
    `v1=${'a'.repeat(64)}`,
    `t=abc,v1=${'a'.repeat(64)}`,
    `t=1793156400,v1=${'A'.repeat(64)}`,
    `t=1793156400,v1=${'a'.repeat(63)}`,
  ])('모양이 틀린 머리말(%j)은 받지 않는다', (header) => {
    expect(accepts(header)).toBe(false);
  });
});
