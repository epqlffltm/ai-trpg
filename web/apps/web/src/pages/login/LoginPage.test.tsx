// web/apps/web/src/pages/login/LoginPage.test.tsx
// 로그인 두 단계를 화면에서 따라가 본다. 서버는 가짜 fetch 다.

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { getSession } from '../../api/session';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const EMPTY_PAGE = { items: [], total: 0 };

/** 처음 열 때의 갱신(로그인 안 됨)과 첫 화면의 목록들 */
const LOGGED_OUT_START = {
  [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
  'GET /api/v1/game/listings': () => json(200, EMPTY_PAGE),
  'GET /api/v1/asset/listings/characters': () => json(200, EMPTY_PAGE),
  'GET /api/v1/game/tables': () => json(200, EMPTY_PAGE),
  'GET /api/v1/chat/conversations': () => json(200, EMPTY_PAGE),
  'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
};

async function enterCredentials() {
  await userEvent.type(await screen.findByLabelText('아이디'), 'player1');
  await userEvent.type(screen.getByLabelText('비밀번호'), 'pw-1234-long');
  await userEvent.click(screen.getByRole('button', { name: '다음' }));
}

describe('LoginPage', () => {
  it('아이디와 비밀번호, 코드를 거쳐 로그인하고 첫 화면으로 간다', async () => {
    const { seen } = installFakeFetch({
      ...LOGGED_OUT_START,
      'POST /api/v1/auth/login': () => json(202, { detail: '보냈다', login_ticket: 'ticket-1' }),
      'POST /api/v1/auth/login/verify': () => json(200, tokens('access-1')),
    });
    renderApp('/login');

    await enterCredentials();
    await userEvent.type(await screen.findByLabelText('인증 코드'), '123456');
    await userEvent.click(screen.getByRole('button', { name: '로그인' }));

    expect(await screen.findByText('TRPG 이어하기')).toBeInTheDocument();
    expect(getSession()?.accessToken).toBe('access-1');
    expect(seen.find((request) => request.url === '/api/v1/auth/login/verify')?.body).toEqual({
      login_ticket: 'ticket-1',
      code: '123456',
    });
  });

  it('아이디나 비밀번호가 틀리면 같은 문구로 알린다', async () => {
    installFakeFetch({
      ...LOGGED_OUT_START,
      'POST /api/v1/auth/login': () => json(401, { detail: '틀렸다' }),
    });
    renderApp('/login');

    await enterCredentials();

    expect(await screen.findByRole('alert')).toHaveTextContent('아이디 또는 비밀번호가 맞지 않습니다');
  });

  it('시도가 너무 많으면 남은 초를 보이고 버튼을 막는다', async () => {
    installFakeFetch({
      ...LOGGED_OUT_START,
      'POST /api/v1/auth/login': () =>
        json(429, { detail: '많다', code: 'too_many_attempts', retry_after: 30 }, { 'Retry-After': '30' }),
    });
    renderApp('/login');

    await enterCredentials();

    expect(await screen.findByRole('button', { name: /30초 뒤에 다시/ })).toBeDisabled();
  });

  it('티켓을 더 쓸 수 없으면 1단계로 돌려보낸다', async () => {
    installFakeFetch({
      ...LOGGED_OUT_START,
      'POST /api/v1/auth/login': () => json(202, { detail: '보냈다', login_ticket: 'ticket-1' }),
      'POST /api/v1/auth/login/verify': () => json(401, { detail: 'x', code: 'login_ticket_invalid' }),
    });
    renderApp('/login');

    await enterCredentials();
    await userEvent.type(await screen.findByLabelText('인증 코드'), '123456');
    await userEvent.click(screen.getByRole('button', { name: '로그인' }));

    expect(await screen.findByLabelText('아이디')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('로그인 시간이 지났습니다');
  });
});
