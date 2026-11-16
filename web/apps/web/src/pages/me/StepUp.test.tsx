// web/apps/web/src/pages/me/StepUp.test.tsx
// 마이페이지의 "결제 본인 확인"(F5). 켜져 있으면 끄기 전에 알리고, 창이 닫혀 있으면 확인한 뒤 끄는지,
// 꺼져 있으면 확인 없이 켜는지, 코드가 틀리면 코드 칸에 알리는지 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const ME = {
  public_id: '0b6f1d2e-0000-4000-8000-000000000001',
  username: 'player_one',
  email: 'one@example.com',
  nickname: '모험가',
  identity: { verified: false, legal_adult: false, adult_content: false },
  guardian_consent: 'none',
  consents_pending: [],
  withdrawal_scheduled_at: null,
  nickname_change_available_at: null,
};

const CLOSED = { enabled: true, open: false, expires_at: null };
const OPEN = { enabled: true, open: true, expires_at: '2026-11-16T01:10:00Z' };
const OFF = { enabled: false, open: false, expires_at: null };

function signedIn(status: Record<string, unknown>, extra: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, ME),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/auth/me/step-up': () => json(200, status),
    ...extra,
  });
}

function section() {
  return within(screen.getByRole('region', { name: '결제 본인 확인' }));
}

describe('결제 본인 확인', () => {
  it('창이 닫혀 있으면 끄기 전에 메일 코드로 확인하고, 확인한 뒤 다시 보낸다', async () => {
    let verified = false;
    const { seen } = signedIn(CLOSED, {
      'PUT /api/v1/auth/me/step-up/setting': () =>
        verified ? json(200, OFF) : json(403, { detail: 'x', code: 'step_up_required' }),
      'POST /api/v1/auth/me/step-up/code': () => json(200, { detail: '인증 메일을 보냈습니다.', sent: true }),
      'POST /api/v1/auth/me/step-up': () => {
        verified = true;
        return json(200, OPEN);
      },
    });
    renderApp('/me');

    expect(await screen.findByText(/청약철회는 다시 켤 때까지 할 수 없습니다/)).toBeInTheDocument();
    await userEvent.click(section().getByRole('button', { name: '본인 확인 끄기' }));
    const stepUp = within(await screen.findByRole('dialog', { name: '본인 확인' }));
    await userEvent.type(stepUp.getByLabelText('인증 코드'), '654321');
    await userEvent.click(stepUp.getByRole('button', { name: '확인' }));

    expect(await section().findByText(/꺼져 있습니다/)).toBeInTheDocument();
    const puts = seen.filter((request) => request.url === '/api/v1/auth/me/step-up/setting');
    expect(puts.map((request) => request.body)).toEqual([{ enabled: false }, { enabled: false }]);
  });

  it('꺼져 있으면 확인 없이 켠다', async () => {
    const { seen } = signedIn(OFF, { 'PUT /api/v1/auth/me/step-up/setting': () => json(200, CLOSED) });
    renderApp('/me');

    await userEvent.click(await screen.findByRole('button', { name: '본인 확인 켜기' }));

    expect(await section().findByRole('button', { name: '본인 확인 끄기' })).toBeInTheDocument();
    expect(seen.some((request) => request.url === '/api/v1/auth/me/step-up/code')).toBe(false);
  });

  it('열려 있으면 언제까지 다시 묻지 않는지 보인다', async () => {
    signedIn(OPEN);
    renderApp('/me');

    expect(await screen.findByText(/까지 다시 묻지 않습니다/)).toBeInTheDocument();
  });

  it('코드가 틀리면 코드 칸에 알리고 창을 열어 둔다', async () => {
    signedIn(CLOSED, {
      'PUT /api/v1/auth/me/step-up/setting': () => json(403, { detail: 'x', code: 'step_up_required' }),
      'POST /api/v1/auth/me/step-up/code': () => json(200, { detail: '인증 메일을 보냈습니다.', sent: true }),
      'POST /api/v1/auth/me/step-up': () => json(400, { detail: 'x', code: 'step_up_code_invalid' }),
    });
    renderApp('/me');

    await userEvent.click(await screen.findByRole('button', { name: '본인 확인 끄기' }));
    const stepUp = within(await screen.findByRole('dialog', { name: '본인 확인' }));
    await userEvent.type(stepUp.getByLabelText('인증 코드'), '000000');
    await userEvent.click(stepUp.getByRole('button', { name: '확인' }));

    expect((await stepUp.findAllByText('인증 코드가 올바르지 않거나 만료되었습니다.')).length).toBeGreaterThan(0);
    expect(screen.getByRole('dialog', { name: '본인 확인' })).toBeInTheDocument();
  });

  it('코드를 너무 자주 받으려 하면 기다릴 초를 알린다', async () => {
    signedIn(CLOSED, {
      'PUT /api/v1/auth/me/step-up/setting': () => json(403, { detail: 'x', code: 'step_up_required' }),
      'POST /api/v1/auth/me/step-up/code': () => json(429, { detail: 'x', code: 'step_up_code_unavailable', retry_after: 42 }),
    });
    renderApp('/me');

    await userEvent.click(await screen.findByRole('button', { name: '본인 확인 끄기' }));
    const stepUp = within(await screen.findByRole('dialog', { name: '본인 확인' }));

    expect(await stepUp.findByText('코드를 너무 자주 요청했습니다. 42초 뒤에 다시 시도하세요.')).toBeInTheDocument();
    expect(stepUp.getByRole('button', { name: /코드 다시 받기 \(4\d초\)/ })).toBeDisabled();
  });
});
