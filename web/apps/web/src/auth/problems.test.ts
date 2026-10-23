// web/apps/web/src/auth/problems.test.ts
// 가입과 비밀번호 재설정의 실패를 화면 명세 A2 의 표대로 바꾸는지(막은 IP 포함), 돌아갈 주소와 재설정 링크를 바르게 읽는지 본다.

import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/errors';
import { installFakeFetch, json } from '../test/fakeFetch';
import { apiRequest } from '../api/http';
import { parseResetLink } from '../pages/password/resetLink';
import { describeLoginProblem } from './loginProblem';
import { describePasswordProblem } from './passwordProblem';
import { safeReturnPath } from './safeReturnPath';
import { describeSignupProblem } from './signupProblem';

function apiError(status: number, extra: Partial<ConstructorParameters<typeof ApiError>[0]> = {}) {
  return new ApiError({ status, detail: '서버의 글', ...extra });
}

describe('describeSignupProblem', () => {
  it('티켓을 쓸 수 없으면 1단계부터 다시다', () => {
    expect(describeSignupProblem(apiError(400, { code: 'signup_ticket_invalid' }), 'profile')).toMatchObject({
      restart: true,
    });
  });

  it('동의의 판이 바뀌었으면 다시 읽게 한다', () => {
    const problem = describeSignupProblem(apiError(400, { fields: { consents: ['옛 판'] } }), 'profile');
    expect(problem).toMatchObject({ consentsChanged: true });
  });

  it('칸의 오류는 칸마다, 칸을 가르지 않는 오류는 글로 보인다', () => {
    const problem = describeSignupProblem(
      apiError(400, { fields: { username: ['이미 있다'], non_field_errors: ['비밀번호가 아이디와 비슷하다'] } }),
      'profile',
    );
    expect(problem).toMatchObject({ message: '비밀번호가 아이디와 비슷하다', fields: { username: '이미 있다' } });
  });

  it('이미 가입을 마친 이메일이면 로그인으로 보낸다', () => {
    expect(describeSignupProblem(apiError(409, { code: 'email_registered' }), 'profile')).toMatchObject({
      goToLogin: true,
    });
  });

  it('방금 다른 가입이 이름을 가져갔으면 다른 것을 고르게 한다', () => {
    expect(describeSignupProblem(apiError(409), 'profile').message).toContain('다른 것을 골라');
  });

  it('코드가 틀리면 서버의 글을 보인다', () => {
    expect(describeSignupProblem(apiError(400), 'code').message).toBe('서버의 글');
  });
});

describe('막은 IP(#638)', () => {
  it('가입과 로그인의 어느 단계든 막혔다고 알린다', () => {
    const blocked = apiError(403, { code: 'network_blocked', requestId: 'r-1' });
    expect(describeSignupProblem(blocked, 'email')).toEqual({ message: expect.stringContaining('제한되었습니다'), requestId: 'r-1' });
    expect(describeLoginProblem(blocked, 'credentials').message).toContain('제한되었습니다');
    expect(describeLoginProblem(blocked, 'code').message).toContain('제한되었습니다');
  });
});

describe('describePasswordProblem', () => {
  it('새 비밀번호가 규칙에 어긋나면 그 칸에 보인다', () => {
    const problem = describePasswordProblem(apiError(400, { fields: { new_password: ['너무 흔하다'] } }), 'confirm');
    expect(problem).toMatchObject({ fields: { new_password: '너무 흔하다' } });
    expect(problem.restart).toBeUndefined();
  });

  it('링크가 틀렸거나 만료됐으면 다시 받게 한다', () => {
    expect(describePasswordProblem(apiError(400), 'confirm')).toMatchObject({ restart: true });
  });

  it('요청이 많으면 기다릴 초를 준다', () => {
    expect(describePasswordProblem(apiError(429, { retryAfter: 20 }), 'request')).toMatchObject({ waitSeconds: 20 });
  });
});

describe('서버의 칸 오류', () => {
  it('안쪽에 칸이 있는 오류(동의의 항목마다)도 바깥 칸의 글로 모은다', async () => {
    installFakeFetch({
      'POST /api/v1/auth/signup/complete': () => json(400, { consents: { terms: ['옛 판이다'] }, detail: '틀렸다' }),
    });

    const error = (await apiRequest('/api/v1/auth/signup/complete', { method: 'POST', body: {} }).catch(
      (caught: unknown) => caught,
    )) as ApiError;

    expect(error.fields).toEqual({ consents: ['옛 판이다'] });
  });
});

describe('parseResetLink', () => {
  it('# 뒤의 이메일과 토큰을 읽는다', () => {
    expect(parseResetLink('#email=a%40b.c&token=t-1')).toEqual({ email: 'a@b.c', token: 't-1' });
  });

  it('하나라도 없으면 null', () => {
    expect(parseResetLink('#email=a%40b.c')).toBeNull();
    expect(parseResetLink('')).toBeNull();
  });
});

describe('safeReturnPath 의 인증 화면', () => {
  it.each(['/signup', '/password/forgot', '/reset-password', '/login?x=1'])('%s 에서 왔으면 첫 화면으로', (path) => {
    expect(safeReturnPath(path)).toBe('/');
  });

  it('이름이 비슷한 다른 경로는 그대로다', () => {
    expect(safeReturnPath('/signups-archive')).toBe('/signups-archive');
  });
});
