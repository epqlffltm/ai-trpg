// web/apps/web/src/pages/limited/LimitedSession.test.tsx
// 토큰이 인증 서버에만 통하는 동안의 화면. 어느 경로든 다시 동의나 탈퇴 취소만 보이고, 마치면 새 토큰으로 원래 화면이 뜨는지 본다.
// 그동안의 틀(Stitch 7번)은 위쪽 줄에 이름과 로그아웃만 있고, 카드 아래에도 로그아웃이 있다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { getSession } from '../../api/session';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

function termsState(extra: Record<string, unknown> = {}) {
  return { item: 'terms', version: 1, required: true, pending: true, agreed_version: null, agreed_at: null, ...extra };
}

/** 처음 갱신은 first, 그다음부터는 모든 서버에 통하는 토큰 */
function refreshes(first: Record<string, unknown>) {
  let count = 0;
  return () => {
    count += 1;
    return json(200, count === 1 ? tokens('limited', first) : tokens('full'));
  };
}

describe('다시 동의', () => {
  it('어느 경로로 와도 다시 동의만 보이고, 동의하면 새 토큰으로 그 화면이 뜬다', async () => {
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: refreshes({ consents_pending: ['terms'] }),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
      'GET /api/v1/auth/me/consents': () => json(200, { items: [termsState()] }),
      'PUT /api/v1/auth/me/consents/terms': () => json(200, { items: [termsState({ pending: false, agreed_version: 1 })] }),
    });
    renderApp('/chat/later');

    expect(await screen.findByRole('heading', { name: '바뀐 약관에 동의해 주세요' })).toBeInTheDocument();
    const submit = await screen.findByRole('button', { name: '동의하고 계속하기' });
    expect(submit).toBeDisabled();

    await userEvent.click(await screen.findByLabelText('[필수] 이용약관'));
    await userEvent.click(submit);

    expect(await screen.findByRole('heading', { name: 'chat' })).toBeInTheDocument();
    expect(getSession()?.accessToken).toBe('full');
    expect(seen.find((request) => request.method === 'PUT')?.body).toEqual({ version: 1 });
    // 인증 서버에만 통하는 토큰으로는 다른 서버를 부르지 않는다(동의한 뒤의 화면은 새 토큰으로 부른다)
    expect(seen.some((request) => request.url.startsWith('/api/v1/game/') && request.headers.get('Authorization') === 'Bearer limited')).toBe(false);
  });

  it('판이 또 바뀌었으면 다시 읽고 체크를 비운다', async () => {
    let reads = 0;
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: refreshes({ consents_pending: ['terms'] }),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
      'GET /api/v1/auth/me/consents': () => {
        reads += 1;
        return json(200, { items: [termsState()] });
      },
      'PUT /api/v1/auth/me/consents/terms': () => json(409, { detail: '판이 바뀌었다', code: 'consent_outdated' }),
    });
    renderApp('/');

    await userEvent.click(await screen.findByLabelText('[필수] 이용약관'));
    await userEvent.click(screen.getByRole('button', { name: '동의하고 계속하기' }));

    expect(await screen.findByText(/문서의 판이 바뀌었습니다/)).toBeInTheDocument();
    expect(screen.getByLabelText('[필수] 이용약관')).not.toBeChecked();
    expect(reads).toBe(2);
  });

  it('화면이 갖지 않은 판이면 받지 않는다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: refreshes({ consents_pending: ['terms'] }),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
      'GET /api/v1/auth/me/consents': () => json(200, { items: [termsState({ version: 99, agreed_version: 1 })] }),
    });
    renderApp('/');

    expect(await screen.findByText(/새 판의 문서가 아직 없습니다/)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText('[필수] 이용약관'));
    expect(screen.getByRole('button', { name: '동의하고 계속하기' })).toBeDisabled();
  });

  it('로그인, 가입, 비밀번호의 화면은 막지 않는다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: refreshes({ consents_pending: ['terms'] }),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    });
    renderApp('/password/forgot');

    expect(await screen.findByRole('heading', { name: '비밀번호 찾기' })).toBeInTheDocument();
  });
});

describe('탈퇴 유예', () => {
  it('지울 시각을 보이고, 취소하면 새 토큰으로 그 화면이 뜬다', async () => {
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: refreshes({ withdrawal_scheduled_at: '2026-10-29T06:00:00Z' }),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
      'DELETE /api/v1/auth/me/withdrawal': () => json(200, { withdrawal_scheduled_at: null }),
    });
    renderApp('/chat/later');

    expect(await screen.findByRole('heading', { name: '탈퇴를 기다리는 중입니다' })).toBeInTheDocument();
    expect(screen.getByText(/2026년 10월/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '탈퇴 취소하기' }));

    expect(await screen.findByRole('heading', { name: 'chat' })).toBeInTheDocument();
    expect(getSession()?.accessToken).toBe('full');
    expect(seen.filter((request) => request.url === REFRESH_PATH)).toHaveLength(2);
  });

  it('취소가 실패하면 그 자리에 알리고 막은 채로 둔다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: refreshes({ withdrawal_scheduled_at: '2026-10-29T06:00:00Z' }),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
      'DELETE /api/v1/auth/me/withdrawal': () => json(503, { detail: '잠시' }),
    });
    renderApp('/');

    await userEvent.click(await screen.findByRole('button', { name: '탈퇴 취소하기' }));

    expect(await screen.findByText(/처리하지 못했습니다/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '탈퇴를 기다리는 중입니다' })).toBeInTheDocument();
    expect(getSession()?.accessToken).toBe('limited');
  });
});

describe('다시 동의·탈퇴 유예의 틀', () => {
  it('왼쪽 메뉴 열, 검색칸, 아래 메뉴 없이 위쪽 줄에 이름과 로그아웃만 있고, 카드의 로그아웃으로 나간다', async () => {
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: refreshes({ withdrawal_scheduled_at: '2026-10-29T06:00:00Z' }),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
      'POST /api/v1/auth/logout': () => new Response(null, { status: 204 }),
    });
    renderApp('/me');

    const card = (await screen.findByRole('heading', { name: '탈퇴를 기다리는 중입니다' })).closest('main') as HTMLElement;
    expect(screen.queryByRole('complementary', { name: '사이트 메뉴' })).toBeNull();
    expect(screen.queryByRole('search', { name: '작품 검색' })).toBeNull();
    expect(screen.queryByRole('navigation', { name: '아래 메뉴' })).toBeNull();
    const header = document.querySelector('.app-header') as HTMLElement;
    expect(within(header).getByRole('link', { name: /이매망량의 서재/ })).toHaveAttribute('href', '/');
    expect(within(header).getByRole('button', { name: '로그아웃' })).toBeInTheDocument();
    expect(within(header).queryByRole('button', { name: /알림/ })).toBeNull();

    await userEvent.click(within(card).getByRole('button', { name: '로그아웃' }));

    expect(await screen.findAllByRole('link', { name: '로그인' })).not.toHaveLength(0);
    expect(screen.queryByRole('heading', { name: '탈퇴를 기다리는 중입니다' })).toBeNull();
    expect(seen.some((request) => request.method === 'POST' && request.url === '/api/v1/auth/logout')).toBe(true);
  });

  it('다시 동의의 카드 아래에도 로그아웃이 있다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: refreshes({ consents_pending: ['terms'] }),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
      'GET /api/v1/auth/me/consents': () => json(200, { items: [termsState()] }),
    });
    renderApp('/');

    const card = (await screen.findByRole('heading', { name: '바뀐 약관에 동의해 주세요' })).closest('main') as HTMLElement;
    expect(within(card).getByRole('button', { name: '로그아웃' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '로그아웃' })).toHaveLength(2);
  });
});
