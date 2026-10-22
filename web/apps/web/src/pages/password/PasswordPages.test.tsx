// web/apps/web/src/pages/password/PasswordPages.test.tsx
// 비밀번호 찾기와 재설정 링크의 화면. 링크의 이메일과 토큰을 읽는지, 바꾼 뒤 로그아웃시키는지 본다.

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { getSession } from '../../api/session';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const LINK = '/reset-password#email=a%40example.com&token=tok-1';

describe('ForgotPasswordPage', () => {
  it('가입 여부와 상관없이 같은 안내를 보인다', async () => {
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      'POST /api/v1/auth/password/reset': () => json(202, { detail: '보냈다' }),
    });
    renderApp('/password/forgot');

    await userEvent.type(await screen.findByLabelText('이메일'), ' a@example.com ');
    await userEvent.click(screen.getByRole('button', { name: '링크 받기' }));

    expect(await screen.findByText(/가입된 주소라면/)).toBeInTheDocument();
    expect(seen.find((request) => request.url === '/api/v1/auth/password/reset')?.body).toEqual({ email: 'a@example.com' });
  });
});

describe('ResetPasswordPage', () => {
  it('링크의 이메일과 토큰으로 바꾸고, 로그인 상태를 비우고 로그인으로 보낸다', async () => {
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('still-here')),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
      'POST /api/v1/auth/password/reset/confirm': () => json(200, { detail: '바꿨다' }),
    });
    renderApp(LINK);

    expect(await screen.findByText(/a@example.com 의 비밀번호/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('새 비밀번호'), 'new-pass-1234');
    await userEvent.type(screen.getByLabelText('새 비밀번호 확인'), 'new-pass-1234');
    await userEvent.click(screen.getByRole('button', { name: '바꾸기' }));

    expect(await screen.findByText(/모든 기기에서 로그아웃됐습니다/)).toBeInTheDocument();
    expect(getSession()).toBeNull();
    expect(seen.find((request) => request.url === '/api/v1/auth/password/reset/confirm')?.body).toEqual({
      email: 'a@example.com',
      token: 'tok-1',
      new_password: 'new-pass-1234',
    });
  });

  it('새 비밀번호가 규칙에 어긋나면 그 칸에 서버의 글을 보인다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      'POST /api/v1/auth/password/reset/confirm': () => json(400, { new_password: ['너무 흔한 비밀번호입니다.'] }),
    });
    renderApp(LINK);

    await userEvent.type(await screen.findByLabelText('새 비밀번호'), 'password');
    await userEvent.type(screen.getByLabelText('새 비밀번호 확인'), 'password');
    await userEvent.click(screen.getByRole('button', { name: '바꾸기' }));

    expect(await screen.findByText('너무 흔한 비밀번호입니다.')).toBeInTheDocument();
  });

  it('링크가 만료됐으면 메일을 다시 받게 한다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      'POST /api/v1/auth/password/reset/confirm': () => json(400, { detail: '틀렸다' }),
    });
    renderApp(LINK);

    await userEvent.type(await screen.findByLabelText('새 비밀번호'), 'new-pass-1234');
    await userEvent.type(screen.getByLabelText('새 비밀번호 확인'), 'new-pass-1234');
    await userEvent.click(screen.getByRole('button', { name: '바꾸기' }));

    expect(await screen.findByText(/링크가 틀렸거나 만료됐습니다/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '재설정 메일 다시 받기' })).toHaveAttribute('href', '/password/forgot');
  });

  it('링크에 토큰이 없으면 바꾸는 칸을 보이지 않는다', async () => {
    installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }) });
    renderApp('/reset-password');

    expect(await screen.findByText(/링크가 온전하지 않습니다/)).toBeInTheDocument();
    expect(screen.queryByLabelText('새 비밀번호')).not.toBeInTheDocument();
  });
});
