// web/apps/web/src/auth/loginProblem.test.ts
// 로그인의 실패를 화면 명세 A2 의 표대로 바꾸는지 본다.

import { describe, expect, it } from 'vitest';
import { ApiError, NetworkError } from '../api/errors';
import { describeLoginProblem } from './loginProblem';
import { safeReturnPath } from './safeReturnPath';

function apiError(status: number, extra: Partial<ConstructorParameters<typeof ApiError>[0]> = {}) {
  return new ApiError({ status, detail: '서버의 글', ...extra });
}

describe('describeLoginProblem', () => {
  it('아이디가 없는 것과 비밀번호가 틀린 것(401)을 가르지 않는다', () => {
    expect(describeLoginProblem(apiError(401), 'credentials').message).toContain('아이디 또는 비밀번호');
  });

  it('메일 인증을 마치지 않았으면 가입으로 안내한다', () => {
    const problem = describeLoginProblem(apiError(403, { code: 'email_not_verified' }), 'credentials');
    expect(problem.message).toContain('메일의 인증');
  });

  it('429 면 기다릴 초를 준다', () => {
    const problem = describeLoginProblem(apiError(429, { code: 'too_many_attempts', retryAfter: 30 }), 'credentials');
    expect(problem).toMatchObject({ waitSeconds: 30 });
    expect(problem.message).toContain('30초');
  });

  it('코드 단계의 401 은 처음부터 다시다', () => {
    expect(describeLoginProblem(apiError(401, { code: 'login_ticket_invalid' }), 'code')).toMatchObject({ restart: true });
  });

  it('코드 단계의 400 은 서버의 글과 칸의 오류를 보인다', () => {
    const problem = describeLoginProblem(apiError(400, { fields: { code: ['틀렸다', '또'] } }), 'code');
    expect(problem).toMatchObject({ message: '서버의 글', fields: { code: '틀렸다' } });
  });

  it('서버에 닿지 못하면 그렇게 알린다', () => {
    expect(describeLoginProblem(new NetworkError(new Error('x')), 'code').message).toContain('닿지 못했습니다');
  });

  it('모르는 실패에는 문의할 요청 번호를 붙인다', () => {
    expect(describeLoginProblem(apiError(500, { requestId: 'r-9' }), 'credentials')).toMatchObject({ requestId: 'r-9' });
  });
});

describe('safeReturnPath', () => {
  it.each([
    ['/trpg/tables/1', '/trpg/tables/1'],
    ['//evil.example', '/'],
    ['/\\evil.example', '/'],
    ['https://evil.example', '/'],
    ['/login', '/'],
    [undefined, '/'],
  ])('%s → %s', (candidate, expected) => {
    expect(safeReturnPath(candidate)).toBe(expected);
  });
});
